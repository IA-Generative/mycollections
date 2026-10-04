"""Réindexer ne double plus le corpus (diagnostic d'octobre 2026, P1)."""

from unittest.mock import AsyncMock, patch

from tests.conftest import personne


def _deposer(client, nom, contenu=b"# Titre\n\nPremier paragraphe.\n\n## Section\n\nSecond paragraphe."):
    return client.post(f"/api/ingest/{nom}", files={"file": ("note.md", contenu, "text/markdown")})


def _sources(client, nom):
    return client.get(f"/api/ingest/{nom}/sources").json()


def test_redeposer_ou_reindexer_ne_duplique_ni_les_sources_ni_le_corpus(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        assert _deposer(client, nom).status_code == 200
        assert _deposer(client, nom).status_code == 200
        r = client.post(f"/api/ingest/{nom}/reindex?strategy=length")
        assert r.status_code == 200, r.text
        assert r.json()["files_reindexed"] == 1
        r = client.post(f"/api/ingest/{nom}/reindex?strategy=section")
        assert r.status_code == 200
        cls.return_value.delete_partition.assert_awaited_with(nom)
    sources = _sources(client, nom)
    liste = sources.get("sources", sources) if isinstance(sources, dict) else sources
    assert len([s for s in liste if s.get("filename") == "note.md"]) == 1


def test_un_decoupage_qui_ne_produit_rien_est_refuse_sans_rien_effacer(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        _deposer(client, nom, b"Un texte sans aucun article.")
        r = client.post(f"/api/ingest/{nom}/reindex?strategy=article")
        assert r.status_code == 422
        cls.return_value.delete_partition.assert_not_awaited()
