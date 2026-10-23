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
    a = avis("notes", ancien, est_importeur=True, maintenant=maintenant)
    assert a["code"] == "resana_ancien" and "il y a 12 jours" in a["message"] and a["action"]["url"] == "/c/notes/upload?synchroniser=1"
    assert avis("notes", ancien, est_importeur=False, maintenant=maintenant) is None
    assert avis("notes", {"last_sync_at": maintenant.isoformat()}, est_importeur=True, maintenant=maintenant) is None
    assert avis("notes", {**ancien, "travail": {"etat": "en_cours"}}, est_importeur=True, maintenant=maintenant) is None
    assert avis("notes", {"travail": {"etat": "partiel"}}, est_importeur=True, maintenant=maintenant)["code"] == "resana_incomplet"


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


def test_l_existant_ne_montre_que_ses_collections(client, en_tant_que, faux, privee, creer_collection, nom):
    _arborer(faux)
    en_tant_que(CREATEUR)
    _importer(client, privee, dossier_chemin="Notes")
    r = client.get("/api/sources/resana/existant?espace=e-1&dossier=d-1").json()
    assert [c["collection"] for c in r["meme_dossier"]] == [privee]
    r = client.get("/api/sources/resana/existant", params={"espace": "e-1", "dossier": "d-11", "chemin": "Notes / Comptes rendus"}).json()
    assert [c["collection"] for c in r["dossier_parent"]] == [privee] and not r["meme_dossier"]
    from tests.conftest import personne

    en_tant_que(personne("autre"))
    assert client.get("/api/sources/resana/existant?espace=e-1&dossier=d-1").json()["meme_dossier"] == []


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
    assert a["code"] == "resana_ancien" and "il y a 30 jours" in a["message"]

    col = asyncio.run(get_collection(privee))
    assert asyncio.run(avis_pour(col, CREATEUR))["code"] == "resana_ancien"
    from tests.conftest import SUPERADMIN

    assert asyncio.run(avis_pour(col, SUPERADMIN)) is None  # seul l'importeur peut agir
