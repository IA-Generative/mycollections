"""Ce que le lot 1 ne doit pas casser — écrit pour échouer si quelqu'un « fait le
ménage » plus tard : routes historiques, tables historiques, purge complète,
grille servie même vide, et aucun cookie qui dépasse."""

import os
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from app.services.openrag_client import ResultatPartition
from tests.conftest import TABLES_PAR_COLLECTION, personne

TABLES_HISTORIQUES = {
    "collections": {"name", "scope", "scope_groups_json", "created_by", "archived_at", "system_prompt", "titre", "categorie"},
    "categories": {"cle", "libelle", "description", "ordre"},
    "publications": {"collection_name", "state", "visibility"},
    "publication_history": {"collection_name", "action", "acted_by"},
    "ingest_jobs": {"job_id", "collection_name", "status"},
    "feedback": {"id", "collection_name", "rating"},
    "eval_datasets": {"id", "collection_name", "questions_json"},
    "eval_runs": {"id", "collection_name", "score"},
    "source_files": {"id", "collection_name", "checksum"},
}
TABLES_COLLECTIF = ("demande", "soutien", "abonnement", "proposition", "signalement", "grille_controle", "evenement", "amorce")
#: Les assistants de recherche (ADR-0003) : créées au lot 0, lues par les lots suivants.
TABLES_ASSISTANTS = {
    "assistants": {"id", "titre", "rubrique", "sources_json", "publication_json", "seuil_fiable", "version_publiee", "collection_name", "archive_le"},
    "assistant_versions": {"assistant_id", "numero", "empreinte", "contenu_json", "publie_par_hash", "robot"},
    "consignes": {"assistant_id", "cle", "rang", "quand", "exemples_json", "chercher_json", "repondre", "gabarit"},
    "plans_journal": {"assistant_id", "version", "empreinte", "canal", "planificateur", "consigne", "reponse_fiable", "etapes_json", "duree_ms", "auteur_hash", "robot"},
}


def _colonnes(table):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    finally:
        con.close()


@pytest.mark.parametrize("table,colonnes", TABLES_HISTORIQUES.items())
def test_les_tables_historiques_gardent_leurs_colonnes(client, table, colonnes):
    assert colonnes <= _colonnes(table)


@pytest.mark.parametrize("table", TABLES_COLLECTIF)
def test_les_tables_du_collectif_existent(client, table):
    assert _colonnes(table)


@pytest.mark.parametrize("table,colonnes", TABLES_ASSISTANTS.items())
def test_les_tables_des_assistants_existent(client, table, colonnes):
    assert colonnes <= _colonnes(table)


def test_les_routes_historiques_repondent(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    assert client.get("/api/collections").status_code == 200
    assert client.get(f"/api/collections/{nom}").status_code == 200
    assert client.get(f"/api/collections/{nom}/publication").json()["state"] == "draft"
    assert client.post(f"/api/collections/{nom}/publish", json={"visibility": "group", "alias_enabled": False}).status_code == 200
    assert client.get(f"/api/collections/{nom}/publication/history").status_code == 200
    assert client.get(f"/api/playground/{nom}/bank").status_code == 200
    assert client.get(f"/api/feedback/{nom}").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/api/config").status_code == 200


def test_la_grille_est_servie_meme_vide(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    r = client.get(f"/api/collections/{nom}/grille")
    assert r.status_code == 200
    g = r.json()["grille"]
    assert g["source_licence"] == "" and g["relecture_n"] == 0 and g["complete"] is False


def test_la_purge_vide_aussi_les_tables_du_collectif(client, en_tant_que, creer_collection, nom):
    garant = personne("garant")
    creer_collection(nom, garant)
    en_tant_que(personne("x"))
    client.post(f"/api/collections/{nom}/propositions", json={"cible_type": "fichier", "apres": "v2", "justification": "j"})
    client.post(f"/api/collections/{nom}/signalements", json={"motif": "erreur", "texte": "t"})
    client.post(f"/api/collections/{nom}/abonner")
    en_tant_que(garant)
    client.post(f"/api/collections/{nom}/archive")
    with patch("app.services.collection_store.OpenRAGClient", create=True), patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.delete_partition = AsyncMock(return_value=ResultatPartition(status="ok"))
        r = client.delete(f"/api/collections/{nom}")
    assert r.status_code == 200, r.text
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        for t in TABLES_PAR_COLLECTION:
            assert con.execute(f"SELECT count(*) FROM {t} WHERE collection_name=?", (nom,)).fetchone()[0] == 0, t
        assert con.execute("SELECT count(*) FROM abonnement WHERE objet_type='collection' AND objet_id=?", (nom,)).fetchone()[0] == 0
    finally:
        con.close()


def test_aucun_cookie_ne_depasse(client, en_tant_que, creer_collection, nom):
    """Un cookie de session est admis (une référence), jamais un jeton : < 1 024 o."""
    creer_collection(nom)
    en_tant_que(personne(1))
    for r in (client.get("/api/collections"), client.get("/api/demandes"), client.get(f"/api/collections/{nom}/etat"), client.get("/api/config")):
        for valeur in r.headers.get_list("set-cookie"):
            assert len(valeur) < 1024, "un cookie qui dépasse est jeté par le navigateur"
