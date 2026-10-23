"""Les routes /api/sources/resana : import d'un dossier, synchronisation, et la règle de la v1
(collection privée à la personne qui a importé ; synchronisation réservée à elle).

Un faux service d'export répond à la place de Résana ; OpenRAG est remplacé. Aucun appel réseau.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth import CurrentUser
from app.routers import sources_resana
from app.services.connectors.resana import ClientExportResana
from tests.conftest import SUPERADMIN, personne
from tests.unit._faux_resana import BASE, SECRET, TEMOIN, DocFaux, FauxResana

CREATEUR = personne("createur")
ENTETE = {"Authorization": f"Bearer {TEMOIN}"}


def _doc(ident: str, contenu: str, nom: str | None = None, **champs) -> DocFaux:
    return DocFaux(id=ident, titre=f"Note fictive {ident}", nom_fichier=nom or f"note-{ident}.md", contenu=contenu.encode(), **champs)


@pytest.fixture
def faux(monkeypatch):
    """Le faux service, la tâche de fond attendue sur place, OpenRAG et l'envoi remplacés."""
    service = FauxResana(documents=[_doc("a", "# A\n\nPremier texte fictif."), _doc("b", "# B\n\nDeuxième texte fictif.")])
    monkeypatch.setattr(sources_resana.settings, "resana_export_url", BASE)
    monkeypatch.setattr(sources_resana.settings, "resana_export_secret", SECRET)
    monkeypatch.setattr(sources_resana, "_fabrique", lambda url, secret, jeton: ClientExportResana(url, secret, jeton, transport=service.transport()))

    async def sur_place(collection, travail):
        await travail

    monkeypatch.setattr(sources_resana, "_demarrer", sur_place)
    openrag = MagicMock()
    openrag.delete_partition = AsyncMock()
    openrag.create_partition = AsyncMock()
    monkeypatch.setattr(sources_resana.depot, "OpenRAGClient", MagicMock(return_value=openrag))
    envois = AsyncMock()
    monkeypatch.setattr(sources_resana.depot, "_ingest_content", envois)
    service.openrag, service.envois = openrag, envois
    return service


@pytest.fixture
def privee(creer_collection, nom):
    creer_collection(nom, createur=CREATEUR, scope="private", scope_groups=[])
    return nom


def _importer(client, nom, **extra):
    corps = {"collection": nom, "espace_id": "e-1", "espace_nom": "Alpha fictif", "dossier_id": "d-1", "dossier_chemin": "Notes", **extra}
    return client.post("/api/sources/resana/add", json=corps, headers=ENTETE)


def _envoyes(faux) -> dict[str, str]:
    """{nom de fichier: adresse citée} des fichiers envoyés à l'indexation."""
    return {c.args[1]: c.kwargs["source_path"] for c in faux.envois.await_args_list}


def _sources(nom) -> list[str]:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return sorted(r[0] for r in con.execute("SELECT filename FROM source_files WHERE collection_name = ?", (nom,)))
    finally:
        con.close()


# --- Le drapeau ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "methode,chemin",
    [
        ("get", "/api/sources/resana/espaces"),
        ("get", "/api/sources/resana/espaces/e-1/dossiers"),
        ("post", "/api/sources/resana/add"),
        ("get", "/api/sources/resana/status/x"),
        ("post", "/api/sources/resana/sync/x"),
    ],
)
def test_capacite_eteinte_404(client, en_tant_que, capacites, methode, chemin):
    en_tant_que(CREATEUR)
    capacites(resana=False)
    r = client.request(methode.upper(), chemin, json={} if methode == "post" else None, headers=ENTETE)
    assert r.status_code == 404 and "Fonction désactivée" in r.text


def test_eteinte_par_defaut():
    from app.services import capacites

    assert "resana" in capacites.DRAPEAUX and capacites._defauts()["resana"] is False


# --- Parcourir ----------------------------------------------------------------------------------


def test_espaces_tries_avec_le_jeton_de_la_personne(client, en_tant_que, faux):
    en_tant_que(CREATEUR)
    r = client.get("/api/sources/resana/espaces", headers=ENTETE)
    assert r.status_code == 200
    assert [e["nom"] for e in r.json()["espaces"]] == ["Alpha fictif", "Zêta fictif"]
    assert faux.requetes[0].headers["authorization"] == f"Bearer {TEMOIN}"
    assert faux.requetes[0].headers["x-internal-token"] == SECRET


def test_dossiers_et_apercu(client, en_tant_que, faux):
    en_tant_que(CREATEUR)
    assert client.get("/api/sources/resana/espaces/e-1/dossiers?recherche=not", headers=ENTETE).json()["dossiers"][0]["chemin"] == "Notes"
    assert faux.requetes[-1].url.params["search"] == "not"
    apercu = client.get("/api/sources/resana/espaces/e-1/apercu?dossier=d-1", headers=ENTETE).json()
    assert apercu["total"] == 2 and apercu["documents"][0]["titre"] == "Note fictive a"


def test_session_absente_rend_le_lien_de_connexion(client, en_tant_que, faux):
    faux.pannes["/espaces"] = (409, {"code": "session_absente", "message": "x", "reessayable": False, "url_connexion": "https://monassistant.fake-domain.name/resana"})
    en_tant_que(CREATEUR)
    r = client.get("/api/sources/resana/espaces", headers=ENTETE)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "session_absente" and r.json()["detail"]["url_connexion"].startswith("https://")
    assert "mot de passe" not in r.text


def test_un_401_du_service_ne_deconnecte_pas_l_ecran(client, en_tant_que, faux, monkeypatch):
    monkeypatch.setattr(sources_resana.settings, "resana_export_secret", "autre-secret")
    en_tant_que(CREATEUR)
    r = client.get("/api/sources/resana/espaces", headers=ENTETE)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "appelant_inconnu"


def test_service_non_configure_503(client, en_tant_que, faux, monkeypatch):
    monkeypatch.setattr(sources_resana.settings, "resana_export_url", "")
    en_tant_que(CREATEUR)
    assert client.get("/api/sources/resana/espaces", headers=ENTETE).status_code == 503


# --- Importer -----------------------------------------------------------------------------------


def test_import_prive_dedoublonne_et_cite_resana(client, en_tant_que, faux, privee):
    faux.documents += [
        _doc("c", "# A\n\nPremier texte fictif."),  # même contenu que « a »
        DocFaux(id="d", titre="Binaire fictif", nom_fichier="outil.exe", contenu=b"MZ\x90\x00\x03", mime="application/octet-stream"),
        _doc("e", "# E\n\nAutre texte fictif.", nom="note-a.md"),  # même nom que « a »
    ]
    en_tant_que(CREATEUR)
    r = _importer(client, privee)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 5
    envoyes = _envoyes(faux)
    assert sorted(envoyes) == ["note-a (e).md", "note-a.md", "note-b.md"]
    assert envoyes["note-a.md"] == "https://resana.fake-domain.name/espace-fictif/ged/a"
    statut = client.get(f"/api/sources/resana/status/{privee}").json()
    assert statut["configured"] and statut["est_importeur"] and statut["documents"] == 3
    assert statut["travail"]["etat"] == "termine" and statut["travail"]["ajoutes"] == 3 and statut["travail"]["ecartes"] == 2
    raisons = {e["titre"]: e["raison"] for e in statut["travail"]["documents_ecartes"]}
    assert "même contenu" in raisons["Note fictive c"] and "format" in raisons["Binaire fictif"]
    fiche = client.get(f"/api/collections/{privee}").json()
    assert fiche["scope"] == "private" and fiche["scope_groups"] == [] and fiche["source_type"] == "resana"


def test_import_reserve_au_createur(client, en_tant_que, faux, privee):
    en_tant_que(SUPERADMIN)
    r = _importer(client, privee)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reserve_au_createur"


def test_import_dans_une_collection_partagee_refuse(client, en_tant_que, faux, creer_collection, nom):
    creer_collection(nom, createur=CREATEUR)  # portée « group », groupe des testeurs
    en_tant_que(CREATEUR)
    r = _importer(client, nom)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "collection_non_privee"
    assert not faux.requetes


def test_import_dans_une_collection_non_vide_refuse(client, en_tant_que, faux, privee):
    en_tant_que(CREATEUR)
    assert _importer(client, privee).status_code == 200
    # Déjà reliée : on synchronise ; et une collection qui a des documents ne reçoit pas Résana.
    assert _importer(client, privee).json()["detail"]["code"] == "deja_reliee"
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.execute("UPDATE collections SET source_type = '' WHERE name = ?", (privee,))
    con.commit()
    con.close()
    assert _importer(client, privee).json()["detail"]["code"] == "collection_non_vide"


def test_dossier_vide(client, en_tant_que, faux, privee):
    faux.documents = []
    en_tant_que(CREATEUR)
    r = _importer(client, privee)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "dossier_vide"
    assert client.get(f"/api/collections/{privee}").json()["source_type"] != "resana"


def test_session_perdue_avant_tout_document(client, en_tant_que, faux, privee):
    faux.documents[0].refus = faux.documents[1].refus = (409, "session_absente")
    en_tant_que(CREATEUR)
    assert _importer(client, privee).status_code == 200
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert travail["etat"] == "echec" and travail["code"] == "session_absente"
    assert not faux.envois.await_count and _sources(privee) == []


def test_session_perdue_en_route_garde_l_acquis_et_la_synchro_reprend(client, en_tant_que, faux, privee, monkeypatch):
    monkeypatch.setattr(sources_resana, "TELECHARGEMENTS_PARALLELES", 1)
    faux.documents[1].refus = (409, "session_absente")
    en_tant_que(CREATEUR)
    _importer(client, privee)
    statut = client.get(f"/api/sources/resana/status/{privee}").json()
    assert statut["travail"]["etat"] == "partiel" and statut["travail"]["code"] == "session_absente"
    assert statut["documents"] == 1 and statut["last_sync_at"] is None
    assert _sources(privee) == ["note-a.md"]

    faux.documents[1].refus = None
    faux.envois.reset_mock()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert (travail["etat"], travail["ajoutes"], travail["inchanges"]) == ("termine", 1, 1)
    assert _sources(privee) == ["note-a.md", "note-b.md"]


def test_le_plafond_se_franchit_en_plusieurs_synchronisations(client, en_tant_que, faux, privee, monkeypatch):
    monkeypatch.setattr(sources_resana, "TELECHARGEMENTS_PARALLELES", 1)
    monkeypatch.setattr(sources_resana, "OCTETS_MAX_TOTAL", 40)
    en_tant_que(CREATEUR)
    _importer(client, privee)
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert travail["etat"] == "partiel" and travail["code"] == "trop_volumineux_total" and _sources(privee) == ["note-a.md"]
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _sources(privee) == ["note-a.md", "note-b.md"]


def test_un_grand_dossier_se_prepare_puis_s_importe(client, en_tant_que, faux, privee, monkeypatch):
    dormi = []

    async def dormir(s):
        dormi.append(s)

    monkeypatch.setattr(ClientExportResana, "_dormir", staticmethod(dormir))
    faux.preparations = 1
    en_tant_que(CREATEUR)
    r = client.get("/api/sources/resana/espaces/e-1/apercu?dossier=d-1", headers=ENTETE)
    assert r.status_code == 202 and r.json() == {"en_preparation": True, "dossiers_lus": 12, "dossiers": 40} and r.headers["retry-after"] == "10"
    faux.preparations = 2
    r = _importer(client, privee)
    assert r.status_code == 200 and r.json()["total"] is None
    statut = client.get(f"/api/sources/resana/status/{privee}").json()
    assert statut["travail"]["etat"] == "termine" and statut["documents"] == 2
    assert dormi == [10.0]


def test_une_synchro_sur_un_dossier_vide_ne_retire_rien(client, en_tant_que, faux, privee):
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.documents = []
    r = client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "dossier_vide"
    assert _sources(privee) == ["note-a.md", "note-b.md"]


def test_un_document_refuse_est_ecarte_les_autres_passent(client, en_tant_que, faux, privee):
    faux.documents[0].refus = (403, "hors_droits")
    en_tant_que(CREATEUR)
    _importer(client, privee)
    statut = client.get(f"/api/sources/resana/status/{privee}").json()
    assert sorted(_envoyes(faux)) == ["note-b.md"] and statut["travail"]["ecartes"] == 1


# --- Synchroniser -------------------------------------------------------------------------------


def test_synchroniser_ne_reindexe_que_si_un_condensat_change(client, en_tant_que, faux, privee):
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.openrag.delete_partition.reset_mock()
    faux.envois.reset_mock()

    r = client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert r.status_code == 200
    assert client.get(f"/api/sources/resana/status/{privee}").json()["travail"]["etat"] == "a_jour"
    assert not faux.openrag.delete_partition.await_count and not faux.envois.await_count

    faux.documents = [_doc("b", "# B\n\nDeuxième texte fictif, corrigé."), _doc("f", "# F\n\nNouveau texte fictif.")]
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert (travail["ajoutes"], travail["modifies"], travail["retires"], travail["inchanges"]) == (1, 1, 1, 0)
    assert faux.openrag.delete_partition.await_count == 1
    assert sorted(_envoyes(faux)) == ["note-b.md", "note-f.md"]
    assert _sources(privee) == ["note-b.md", "note-f.md"]


def test_synchroniser_reserve_a_l_importeur(client, en_tant_que, faux, privee):
    en_tant_que(CREATEUR)
    _importer(client, privee)
    en_tant_que(SUPERADMIN)
    r = client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reserve_a_l_importeur"
    assert client.get(f"/api/sources/resana/status/{privee}").json()["est_importeur"] is False
    en_tant_que(personne("lecteur"))
    assert client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE).status_code == 404
    assert client.get(f"/api/sources/resana/status/{privee}").status_code == 404


# --- Rester privée ------------------------------------------------------------------------------


def test_la_fiche_ne_rouvre_pas_une_collection_resana(client, en_tant_que, faux, privee):
    en_tant_que(CREATEUR)
    _importer(client, privee)
    for champs in ({"scope": "public"}, {"scope_groups": ["/g/mirai-beta-testeurs"]}, {"source_type": "drive"}, {"source_config_json": "{}"}):
        r = client.patch(f"/api/collections/{privee}", json=champs)
        assert r.status_code == 409, champs
    assert client.patch(f"/api/collections/{privee}", json={"titre": "Notes fictives", "scope": "private", "scope_groups": []}).status_code == 200
    assert client.post(f"/api/collections/{privee}/publish", json={"visibility": "all"}).status_code == 409


def test_on_ne_devient_pas_resana_par_la_fiche(client, en_tant_que, privee):
    en_tant_que(CREATEUR)
    assert client.patch(f"/api/collections/{privee}", json={"source_type": "resana"}).status_code == 409


def test_le_jeton_ne_laisse_aucune_trace(client, en_tant_que, faux, privee, caplog):
    caplog.set_level(logging.DEBUG)
    faux.documents[1].refus = (403, "hors_droits")
    en_tant_que(CREATEUR)
    reponses = [_importer(client, privee).text, client.get(f"/api/sources/resana/status/{privee}").text, client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE).text]
    assert all(TEMOIN not in t for t in reponses)
    assert TEMOIN not in caplog.text
    chemin = os.environ["DATABASE_URL"].split("///")[-1]
    con = sqlite3.connect(chemin)
    try:
        con.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        con.close()
    assert TEMOIN.encode() not in open(chemin, "rb").read()


def test_un_tiers_sans_droit_ne_voit_rien(client, en_tant_que, faux, privee):
    en_tant_que(CurrentUser(sub="etranger", username="e", groups=["/g/rien"]))
    assert _importer(client, privee).status_code == 404
