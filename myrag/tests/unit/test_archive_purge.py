"""Tests for the archive / unarchive / purge flow on collections.

These tests hit the real DB configured by DATABASE_URL. Each test cleans the
collection it creates so they can run against the dev SQLite without state
leakage. The OpenRAG client is mocked — we don't want these tests to depend
on a reachable OpenRAG instance.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def collection_name(request):
    """Unique collection name per test; auto-cleaned after."""
    name = f"pytest-{request.node.name}"[:60]

    async def _purge():
        import sqlite3
        from app.config import settings
        # Best-effort direct DB cleanup (bypasses archive requirement)
        if "sqlite" in settings.database_url:
            db_path = settings.database_url.split("///")[-1]
            try:
                conn = sqlite3.connect(db_path)
                for t in (
                    "source_files", "eval_runs", "eval_datasets", "feedback",
                    "ingest_jobs", "publication_history", "publications",
                ):
                    conn.execute(f"DELETE FROM {t} WHERE collection_name = ?", (name,))
                conn.execute("DELETE FROM collections WHERE name = ?", (name,))
                conn.commit()
                conn.close()
            except Exception:
                pass

    yield name
    asyncio.run(_purge())


class TestArchiveUnarchive:
    @patch("app.routers.collections.OpenRAGClient")
    def test_archive_flags_collection(self, mock_client_cls, client, collection_name):
        mock_client_cls.return_value.create_partition = AsyncMock()
        client.post("/api/collections", json={"name": collection_name})

        resp = client.post(f"/api/collections/{collection_name}/archive")
        assert resp.status_code == 200
        body = resp.json()
        assert body["collection"] == collection_name
        assert body["archived_at"] is not None

    @patch("app.routers.collections.OpenRAGClient")
    def test_archive_unknown_returns_404(self, mock_client_cls, client):
        resp = client.post("/api/collections/pytest-nope-xyz-123/archive")
        assert resp.status_code == 404

    @patch("app.routers.collections.OpenRAGClient")
    def test_archived_hidden_from_default_list(self, mock_client_cls, client, collection_name):
        mock_client_cls.return_value.create_partition = AsyncMock()
        mock_client_cls.return_value.list_models = AsyncMock(return_value={"data": []})
        mock_client_cls.return_value.list_files = AsyncMock(return_value=[])
        client.post("/api/collections", json={"name": collection_name})
        client.post(f"/api/collections/{collection_name}/archive")

        default_list = client.get("/api/collections").json()["collections"]
        names = [c["name"] for c in default_list]
        assert collection_name not in names

    @patch("app.routers.collections.OpenRAGClient")
    def test_archived_visible_with_include_archived(self, mock_client_cls, client, collection_name):
        mock_client_cls.return_value.create_partition = AsyncMock()
        mock_client_cls.return_value.list_models = AsyncMock(return_value={"data": []})
        mock_client_cls.return_value.list_files = AsyncMock(return_value=[])
        client.post("/api/collections", json={"name": collection_name})
        client.post(f"/api/collections/{collection_name}/archive")

        full_list = client.get("/api/collections?include_archived=true").json()["collections"]
        names = [c["name"] for c in full_list]
        assert collection_name in names

    @patch("app.routers.collections.OpenRAGClient")
    def test_unarchive_restores(self, mock_client_cls, client, collection_name):
        mock_client_cls.return_value.create_partition = AsyncMock()
        client.post("/api/collections", json={"name": collection_name})
        client.post(f"/api/collections/{collection_name}/archive")

        resp = client.post(f"/api/collections/{collection_name}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None


class TestPurge:
    @patch("app.routers.collections.OpenRAGClient")
    def test_purge_requires_archived_first(self, mock_client_cls, client, collection_name):
        mock_client_cls.return_value.create_partition = AsyncMock()
        client.post("/api/collections", json={"name": collection_name})

        resp = client.delete(f"/api/collections/{collection_name}")
        assert resp.status_code == 409
        assert "archived" in resp.json()["detail"].lower()

    @patch("app.services.openrag_client.OpenRAGClient.delete_partition", new_callable=AsyncMock)
    @patch("app.routers.collections.OpenRAGClient")
    def test_purge_cascades_all_tables(
        self, mock_router_client_cls, mock_delete_partition, client, collection_name
    ):
        mock_router_client_cls.return_value.create_partition = AsyncMock()
        mock_delete_partition.return_value = {"status": "ok"}
        client.post("/api/collections", json={"name": collection_name})
        client.post(f"/api/collections/{collection_name}/archive")

        resp = client.delete(f"/api/collections/{collection_name}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "purged"
        assert body["openrag"] == "ok"
        assert body["rows_deleted"]["collections"] == 1

        # Collection must be gone
        resp2 = client.get(f"/api/collections/{collection_name}")
        assert resp2.status_code == 404

    @patch("app.routers.collections.OpenRAGClient")
    def test_purge_nonexistent_returns_404(self, mock_client_cls, client):
        resp = client.delete("/api/collections/pytest-nope-purge-xyz")
        assert resp.status_code == 404
