"""Le périmètre d'une collection Résana : inventaire, exclusions, couverture, invitation à mettre
l'index à jour — fonctions pures, et leur usage par les routes (faux service, aucun appel réseau)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from app.services.connectors.resana import DocumentResana, Dossier
from app.services.resana_perimetre import avis, couverture, dans_le_perimetre, exclus_effectifs, inventaire
from tests.unit._faux_resana import DocFaux
from tests.unit.test_resana_routes import CREATEUR, ENTETE, _importer, _sources, faux, privee  # noqa: F401 — fixtures

ARBRE = [
    Dossier("d-1", "Racine", None, "Racine"),
    Dossier("d-11", "Comptes rendus", "d-1", "Racine / Comptes rendus"),
    Dossier("d-111", "2026", "d-11", "Racine / Comptes rendus / 2026"),
    Dossier("d-12", "Procédures", "d-1", "Racine / Procédures"),
    Dossier("d-9", "Ailleurs", None, "Ailleurs"),
]


def _d(ident: str, dossier: str, mo: float | None = 1.0) -> DocumentResana:
    return DocumentResana(id=ident, titre=ident, nom_fichier=f"{ident}.md", mime="", dossier_id=dossier, chemin="", url_consultation="", taille_approx_mo=mo)


DOCS = [_d("r", "d-1"), _d("a", "d-11"), _d("b", "d-111"), _d("c", "d-111", None), _d("p", "d-12")]


def test_inventaire_compte_par_dossier_et_par_sous_arbre():
    racine, noeuds = inventaire("d-1", ARBRE, DOCS)
    assert racine == 1
    vus = {n.id: (n.profondeur, n.documents, n.documents_total, n.taille_approx_mo) for n in noeuds}
    assert vus == {"d-11": (0, 1, 3, 2.0), "d-111": (1, 2, 2, 1.0), "d-12": (0, 1, 1, 1.0)}
    assert [n.id for n in noeuds] == ["d-11", "d-111", "d-12"]  # parcours en profondeur, par titre


def test_exclure_un_dossier_exclut_son_contenu():
    effectifs = exclus_effectifs(["d-11"], ARBRE)
    assert effectifs == {"d-11", "d-111"}
    assert [d.id for d in dans_le_perimetre(DOCS, effectifs)] == ["r", "p"]


def test_couverture():
    assert couverture({"last_sync_at": "x", "documents": {"a": {}}})["couverture"] == "totale"
    c = couverture({"last_sync_at": "x", "documents": {"a": {}}, "perimetre": {"exclus": ["d-11"]}})
    assert (c["couverture"], c["raisons"], c["dossiers_exclus"]) == ("partielle", ["selection"], 1)
    assert couverture({"documents": {"a": {}}, "travail": {"etat": "partiel"}})["raisons"] == ["interrompue"]
    assert couverture({})["raisons"] == ["a_faire"]


def test_l_invitation_seulement_pour_l_importeur_et_quand_c_est_utile():
    maintenant = datetime(2026, 10, 23, tzinfo=timezone.utc)
    ancien = {"last_sync_at": (maintenant - timedelta(days=12)).isoformat()}
    a = avis("notes", ancien, est_importeur=True, maintenant=maintenant, titre="Notes fictives")
    assert a["code"] == "resana_ancien" and a["titre"] == "Notes fictives" and a["action"]["url"] == "/c/notes/upload?synchroniser=1"
    assert a["message"] == "L'index Résana de « Notes fictives » semble ancien (dernière lecture il y a 12 jours). Souhaitez-vous le mettre à jour ?"
    assert avis("notes", ancien, est_importeur=False, maintenant=maintenant) is None
    assert avis("notes", {"last_sync_at": maintenant.isoformat()}, est_importeur=True, maintenant=maintenant) is None
    assert avis("notes", {**ancien, "travail": {"etat": "en_cours"}}, est_importeur=True, maintenant=maintenant) is None
    for etat in ("partiel", "interrompu", "echec"):  # un premier import raté aussi
        assert avis("notes", {"travail": {"etat": etat}}, est_importeur=True, maintenant=maintenant)["code"] == "resana_incomplet"
    assert avis("notes", {"travail": {"etat": "echec"}}, est_importeur=True, maintenant=maintenant)["titre"] == "notes"  # sans titre : l'identifiant
    assert avis("a b/c", ancien, est_importeur=True, maintenant=maintenant)["action"]["url"] == "/c/a%20b%2Fc/upload?synchroniser=1"


# --- Par les routes -----------------------------------------------------------------------------

DOSSIERS_FAUX = [
    {"id": "d-1", "titre": "Notes", "parent_id": None, "chemin": "Notes"},
    {"id": "d-11", "titre": "Comptes rendus", "parent_id": "d-1", "chemin": "Notes / Comptes rendus"},
    {"id": "d-111", "titre": "2026", "parent_id": "d-11", "chemin": "Notes / Comptes rendus / 2026"},
    {"id": "d-12", "titre": "Procédures", "parent_id": "d-1", "chemin": "Notes / Procédures"},
]


def _arborer(faux):
    faux.dossiers = DOSSIERS_FAUX
    faux.documents = [
        DocFaux(id="a", titre="A", nom_fichier="a.md", contenu=b"# A\n\nTexte fictif a.", dossier_id="d-1"),
        DocFaux(id="b", titre="B", nom_fichier="b.md", contenu=b"# B\n\nTexte fictif b.", dossier_id="d-11"),
        DocFaux(id="c", titre="C", nom_fichier="c.md", contenu=b"# C\n\nTexte fictif c.", dossier_id="d-111"),
        DocFaux(id="p", titre="P", nom_fichier="p.md", contenu=b"# P\n\nTexte fictif p.", dossier_id="d-12"),
    ]


def test_l_inventaire_par_la_route(client, en_tant_que, faux):
    _arborer(faux)
    en_tant_que(CREATEUR)
    r = client.get("/api/sources/resana/espaces/e-1/inventaire?dossier=d-1", headers=ENTETE).json()
    assert r["total"] == 4 and r["documents_a_la_racine"] == 1
    assert [(d["id"], d["documents_total"]) for d in r["dossiers"]] == [("d-11", 2), ("d-111", 1), ("d-12", 1)]


def test_importer_une_partie_puis_elargir(client, en_tant_que, faux, privee):
    _arborer(faux)
    en_tant_que(CREATEUR)
    assert _importer(client, privee, exclus=["d-11"]).status_code == 200
    assert _sources(privee) == ["a.md", "p.md"]
    statut = client.get(f"/api/sources/resana/status/{privee}").json()
    assert (statut["couverture"], statut["raisons"], statut["exclus"]) == ("partielle", ["selection"], ["d-11"])
    assert (statut["documents_perimetre"], statut["documents_disponibles"]) == (2, 4)
    resume = client.get(f"/api/collections/{privee}").json()["source_resume"]
    assert resume["type"] == "resana" and resume["couverture"] == "partielle"

    # Élargir : le dossier exclu entre dans l'index ; resserrer : il en sort.
    client.post(f"/api/sources/resana/sync/{privee}", json={"exclus": []}, headers=ENTETE)
    assert _sources(privee) == ["a.md", "b.md", "c.md", "p.md"]
    assert client.get(f"/api/sources/resana/status/{privee}").json()["couverture"] == "totale"
    client.post(f"/api/sources/resana/sync/{privee}", json={"exclus": ["d-111", "d-12"]}, headers=ENTETE)
    assert _sources(privee) == ["a.md", "b.md"]


def test_une_selection_vide_echoue_sans_rien_retirer(client, en_tant_que, faux, privee):
    _arborer(faux)
    en_tant_que(CREATEUR)
    _importer(client, privee)
    client.post(f"/api/sources/resana/sync/{privee}", json={"exclus": ["d-11", "d-12"]}, headers=ENTETE)
    faux.documents = faux.documents[1:]  # il ne reste rien hors des dossiers exclus
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert travail["etat"] == "echec" and travail["code"] == "selection_vide"
    assert _sources(privee) == ["a.md"]


def test_l_existant_ne_montre_que_ses_collections_sur_cet_espace(client, en_tant_que, faux, privee, creer_collection, nom):
    _arborer(faux)
    en_tant_que(CREATEUR)
    _importer(client, privee, dossier_chemin="Notes")
    r = client.get("/api/sources/resana/existant?espace=e-1").json()
    assert [c["collection"] for c in r["collections"]] == [privee] and r["collections"][0]["chemins"] == ["Notes"]
    assert client.get("/api/sources/resana/existant?espace=e-2").json()["collections"] == []
    from tests.conftest import personne

    en_tant_que(personne("autre"))
    assert client.get("/api/sources/resana/existant?espace=e-1").json()["collections"] == []


def _vieillir(nom: str, jours: int) -> None:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        (brut,) = con.execute("SELECT source_config_json FROM collections WHERE name = ?", (nom,)).fetchone()
        cfg = json.loads(brut)
        cfg["last_sync_at"] = (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat()
        con.execute("UPDATE collections SET source_config_json = ? WHERE name = ?", (json.dumps(cfg), nom))
        con.commit()
    finally:
        con.close()


def test_l_invitation_dans_l_etat_et_pour_la_recherche(client, en_tant_que, faux, privee):
    import asyncio

    from app.routers.sources_resana import avis_pour
    from app.services.collection_store import get_collection

    en_tant_que(CREATEUR)
    _importer(client, privee)
    assert client.get(f"/api/sources/resana/status/{privee}").json()["avis"] is None
    _vieillir(privee, 30)
    a = client.get(f"/api/sources/resana/status/{privee}").json()["avis"]
    assert a["code"] == "resana_ancien" and "il y a 30 jours" in a["message"] and a["titre"]

    col = asyncio.run(get_collection(privee))
    assert asyncio.run(avis_pour(col, CREATEUR))["code"] == "resana_ancien"
    from tests.conftest import SUPERADMIN

    assert asyncio.run(avis_pour(col, SUPERADMIN)) is None  # seul l'importeur peut agir


def test_les_notices_de_la_recherche_pointent_vers_le_front(client, en_tant_que, faux, privee, monkeypatch):
    import asyncio

    from app.routers import recherche
    from app.services.collection_store import get_collection

    monkeypatch.setattr(recherche.settings, "myrag_public_url", "https://mescollections.fake-domain.name/")
    monkeypatch.setattr(recherche.settings, "recherche_url_publique", "https://api.fake-domain.name")
    en_tant_que(CREATEUR)
    _importer(client, privee)
    _vieillir(privee, 30)
    col = asyncio.run(get_collection(privee))
    (n,) = asyncio.run(recherche._notices([privee], {privee: col}, CREATEUR))
    assert n["action"]["url"] == f"https://mescollections.fake-domain.name/c/{privee}/upload?synchroniser=1"
    assert n["collection"] == privee and n["titre"]


# --- Ancrage sur l'espace, périmètre en dossiers -------------------------------------------------


def _purger_resana(*noms):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1], timeout=30)
    try:
        from tests.conftest import TABLES_PAR_COLLECTION

        for n in noms:
            for t in TABLES_PAR_COLLECTION:
                con.execute(f"DELETE FROM {t} WHERE collection_name = ?", (n,))
            con.execute("DELETE FROM collections WHERE name = ?", (n,))
        con.commit()
    finally:
        con.close()


import pytest  # noqa: E402


@pytest.fixture
def espace_libre():
    _purger_resana("resana-e1", "resana-e1-car")
    yield
    _purger_resana("resana-e1", "resana-e1-car")


def _creer(client, **extra):
    corps = {
        "espace_id": "e-1",
        "dossiers": [{"id": "d-11", "chemin": "Notes / Comptes rendus"}, {"id": "d-12", "chemin": "Notes / Procédures"}],
        "titre": "Alpha fictif",
        "entite": "Préfecture fictive",
        **extra,
    }
    return client.post("/api/sources/resana/collections", json=corps, headers=ENTETE)


def test_creer_depuis_un_espace_pose_l_identifiant_et_la_fiche(client, en_tant_que, faux, espace_libre):
    _arborer(faux)
    en_tant_que(CREATEUR)
    r = _creer(client)
    assert r.status_code == 200, r.text
    assert r.json()["collection"] == "resana-e1"
    fiche = client.get("/api/collections/resana-e1").json()
    assert fiche["titre"] == "Alpha fictif" and fiche["scope"] == "private" and fiche["source_type"] == "resana"
    assert fiche["sensitivity"] == "internal", "un espace Résana est interne d'emblée (#134)"
    assert fiche["description"] == "Espace Résana « Alpha fictif » (n° e-1), Préfecture fictive."
    assert fiche["source_resume"]["entite"] == "Préfecture fictive" and fiche["source_resume"]["nb_dossiers"] == 2
    # Les deux dossiers (et leurs sous-dossiers), sans les documents rangés à la racine de l'espace.
    assert _sources("resana-e1") == ["b.md", "c.md", "p.md"]
    statut = client.get("/api/sources/resana/status/resana-e1").json()
    assert statut["espace"]["entite"] == "Préfecture fictive" and [d["id"] for d in statut["dossiers"]] == ["d-11", "d-12"]
    # La fiche d'identité de l'espace est gardée telle que Résana la donne.
    import asyncio

    from app.services.collection_store import get_source_config

    cfg = asyncio.run(get_source_config("resana-e1"))
    assert cfg["espace"] | {} == cfg["espace"] and cfg["espace"]["objet"] == "Essais" and cfg["espace"]["parent_id"] == "123" and cfg["espace"]["cree_le"].startswith("2019")
    # L'adresse commune des documents devient la source de la collection et un site du plug-in.
    assert fiche["source_url"] == "https://resana.fake-domain.name/espace-fictif/ged/"
    assert client.get("/api/collections/resana-e1/sites").json()["motifs"] == ["https://resana.fake-domain.name/espace-fictif/ged/*"]
    # Chaque document part avec son origine.
    meta = faux.envois.await_args_list[0].kwargs["metadata"]
    assert meta["source"] == "resana" and meta["espace"] == "Alpha fictif" and meta["dossier"] and meta["sensitivity"] == "internal"


def test_un_meme_espace_deux_fois_demande_un_suffixe(client, en_tant_que, faux, espace_libre):
    _arborer(faux)
    en_tant_que(CREATEUR)
    assert _creer(client).status_code == 200
    r = _creer(client)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "identifiant_pris" and "Alpha fictif" in r.json()["detail"]["message"]
    p = client.get("/api/sources/resana/proposition?espace=e-1&suffixe=CAR").json()
    assert p == {"identifiant": "resana-e1-car", "disponible": True, "motif": None}
    assert _creer(client, suffixe="CAR").json()["collection"] == "resana-e1-car"


def test_le_prefixe_resana_est_reserve(client, en_tant_que):
    en_tant_que(CREATEUR)
    from unittest.mock import AsyncMock, patch

    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        r = client.post("/api/collections", json={"name": "resana-999", "scope": "private"})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "resana"


def test_un_espace_inaccessible_est_refuse(client, en_tant_que, faux, espace_libre):
    en_tant_que(CREATEUR)
    r = client.post("/api/sources/resana/collections", json={"espace_id": "e-404", "dossiers": [{"id": "d-1"}], "titre": "X"}, headers=ENTETE)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "introuvable"


def test_changer_les_dossiers_met_a_jour_l_index_et_le_journal(client, en_tant_que, faux, espace_libre):
    _arborer(faux)
    en_tant_que(CREATEUR)
    _creer(client)
    r = client.post("/api/sources/resana/sync/resana-e1", json={"dossiers": [{"id": "d-11", "chemin": "Notes / Comptes rendus"}]}, headers=ENTETE)
    assert r.status_code == 200
    assert _sources("resana-e1") == ["b.md", "c.md"]
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1], timeout=30)
    try:
        (detail,) = con.execute("SELECT detail_json FROM evenement WHERE collection_name = 'resana-e1' AND type = 'perimetre.modifie'").fetchone()
    finally:
        con.close()
    assert json.loads(detail)["retires"] == ["Notes / Procédures"]
