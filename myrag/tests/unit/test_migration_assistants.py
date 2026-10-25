"""Une collection publiée a son assistant à une source : créé à la publication (ou au démarrage
pour celles d'avant), jamais deux fois ; mis en sommeil à la dépublication ; réveillé à la
republication ; emporté par la purge."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from app.harnais.contrat import Source
from app.services import assistant_store as store
from app.services.demarrage import MIGRATIONS, migrations_au_demarrage
from app.services.migration_assistants import migrer_collections_publiees
from tests.conftest import GROUPE_TESTEURS, personne

PUBLIER = {"alias_enabled": True, "visibility": "group", "visibility_groups": [GROUPE_TESTEURS]}


@pytest.fixture
def socle():
    with (
        patch("app.services.fiche_socle.synchroniser_fiche", new=AsyncMock(return_value={"nom": "x"})),
        patch("app.services.owui_client.OwuiClient.delete_model", new=AsyncMock(return_value=None)),
    ):
        yield


def _miroir(nom: str) -> dict | None:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.row_factory = sqlite3.Row
    try:
        r = con.execute("SELECT * FROM assistants WHERE collection_name = ?", (nom,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def _compter(table: str, ident: str) -> int:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return con.execute(f"SELECT count(*) FROM {table} WHERE assistant_id = ?", (ident,)).fetchone()[0]
    finally:
        con.close()


def test_une_collection_publiee_devient_un_assistant_a_une_source(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom, titre="Codes NATINF", description="Les infractions et leurs codes.", system_prompt="Réponds avec le code.")
    en_tant_que(personne("createur"))
    assert _miroir(nom) is None, "pas de miroir avant la publication"
    assert client.post(f"/api/collections/{nom}/publish", json=PUBLIER).status_code == 200
    m = _miroir(nom)
    assert m and m["id"] == nom and m["version_publiee"] == 1 and m["archive_le"] is None and m["cree_par_hash"] is None
    numero, fiche = asyncio.run(store.version_publiee(nom))
    assert numero == 1
    assert fiche.sources == [Source(id=nom, type="collection", regime="toujours", rang=1)]
    assert fiche.titre == "Codes NATINF" and fiche.description == "Les infractions et leurs codes."
    assert [c.id for c in fiche.consignes] == ["defaut"]
    assert fiche.consignes[0].quand == "toujours" and fiche.consignes[0].gabarit == "generic" and fiche.consignes[0].repondre == "Réponds avec le code."
    assert fiche.publication.socle is True and fiche.publication.portail is True and fiche.publication.api is True and fiche.publication.fenetre_js is False
    versions = asyncio.run(store.versions(nom))
    assert len(versions) == 1 and versions[0]["robot"] == "migration:collections"
    # Une seconde passe (le démarrage) ne crée rien.
    bilan = asyncio.run(migrer_collections_publiees())
    assert bilan["cree"] == 0 and bilan["erreur"] == 0 and bilan["invalide"] == 0 and bilan["inchange"] >= 1
    assert len(asyncio.run(store.versions(nom))) == 1


def test_une_collection_non_publiee_n_a_pas_de_miroir(client, creer_collection, nom):
    creer_collection(nom)
    asyncio.run(migrer_collections_publiees())
    assert _miroir(nom) is None


def test_depubliee_le_miroir_s_endort_republiee_il_se_reveille(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    assert client.post(f"/api/collections/{nom}/publish", json=PUBLIER).status_code == 200
    assert _miroir(nom)["archive_le"] is None
    assert client.post(f"/api/collections/{nom}/unpublish").status_code == 200
    assert _miroir(nom)["archive_le"] is not None, "dépubliée : en sommeil, pas effacé"
    assert asyncio.run(migrer_collections_publiees())["hors_critere"] >= 1
    assert client.post(f"/api/collections/{nom}/publish", json=PUBLIER).status_code == 200
    assert _miroir(nom)["archive_le"] is None, "republiée : réveillé"
    assert len(asyncio.run(store.versions(nom))) == 1, "le réveil ne refait pas de version"
    types = {r for r in _types(nom)}
    assert {"assistant.derive", "assistant.sommeil", "assistant.reveil"} <= types


def _types(nom: str) -> list[str]:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return [r[0] for r in con.execute("SELECT type FROM evenement WHERE objet_type = 'collection' AND objet_id = ? AND type LIKE 'assistant.%'", (nom,)).fetchall()]
    finally:
        con.close()


def test_la_purge_emporte_le_miroir(client, en_tant_que, creer_collection, nom, socle):
    from app.services import collection_store

    creer_collection(nom)
    en_tant_que(personne("createur"))
    assert client.post(f"/api/collections/{nom}/publish", json=PUBLIER).status_code == 200
    ident = _miroir(nom)["id"]
    assert _compter("assistant_versions", ident) == 1 and _compter("consignes", ident) == 1
    asyncio.run(collection_store.archive_collection(nom))
    with patch("app.services.openrag_client.OpenRAGClient.delete_partition", new=AsyncMock(return_value={"status": "deleted"})):
        rapport = asyncio.run(collection_store.purge_collection(nom))
    assert rapport["status"] == "purged" and rapport["rows_deleted"]["miroir.assistants"] == 1
    assert _miroir(nom) is None
    assert all(_compter(t, ident) == 0 for t in ("assistant_versions", "consignes", "plans_journal"))


def test_le_demarrage_joue_les_migrations_dans_l_ordre(client):
    assert [m.__name__ for m in MIGRATIONS] == ["migrer_vers_questions", "migrer_collections_publiees", "proposer_les_sites_resana"]
    bilan = asyncio.run(migrations_au_demarrage())
    assert set(bilan) == {"migrer_vers_questions", "migrer_collections_publiees", "proposer_les_sites_resana"}
    assert isinstance(bilan["migrer_collections_publiees"], dict)
