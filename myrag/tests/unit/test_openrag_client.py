"""Tests for OpenRAG API client (TDD)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.openrag_client import OpenRAGClient


@pytest.fixture
def client():
    return OpenRAGClient(base_url="http://openrag:8080", admin_token="or-test-token")


class TestOpenRAGClient:
    def test_init(self, client):
        assert client.base_url == "http://openrag:8080"
        assert client.admin_token == "or-test-token"

    def test_headers(self, client):
        headers = client._headers()
        assert headers["Authorization"] == "Bearer or-test-token"
        assert "Content-Type" in headers

    @pytest.mark.asyncio
    async def test_create_partition(self, client):
        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status": "ok"}
            result = await client.create_partition("test-collection")
            mock_post.assert_called_once()
            assert "partition/test-collection" in str(mock_post.call_args)
            assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_upload_chunk(self, client):
        chunk = {
            "content": "Article L110-1 content",
            "filename": "Article-L110-1.md",
            "metadata": {"article": "L110-1"},
        }
        with patch.object(client, "_upload_file", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {"task_status_url": "/indexer/task/123"}
            result = await client.upload_chunk("test-collection", chunk)
            mock_upload.assert_called_once()
            assert result.task_status_url == "/indexer/task/123"

    @pytest.mark.asyncio
    async def test_search(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"documents": [{"content": "result"}]}
            result = await client.search("test-collection", "query", top_k=5)
            mock_get.assert_called_once()
            assert result.documents[0].content == "result"

    @pytest.mark.asyncio
    async def test_list_models(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"data": [{"id": "openrag-test"}]}
            result = await client.list_models()
            assert len(result.data) == 1


@pytest.mark.asyncio
async def test_file_markdown_rend_le_texte_ou_la_raison(client, monkeypatch):
    """#147 : la copie Markdown d'un document, ou pourquoi elle manque."""
    import httpx

    reponses = {
        "/partition/p/file/a/markdown": httpx.Response(200, text="## Titre fictif"),
        "/partition/p/file/b/markdown": httpx.Response(404, json={"detail": "[MARKDOWN_NOT_AVAILABLE]: indexé sans copie"}),
        "/partition/p/file/c/markdown": httpx.Response(404, json={"detail": "[FILE_NOT_FOUND]: absent"}),
        "/partition/p/file/d/markdown": httpx.Response(404, json={"detail": "Not Found"}),
    }
    vrai = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(lambda r: reponses[r.url.path]), **kw))
    assert await client.file_markdown("p", "a") == ("## Titre fictif", "")
    assert await client.file_markdown("p", "b") == (None, "MARKDOWN_NOT_AVAILABLE")
    assert await client.file_markdown("p", "c") == (None, "FILE_NOT_FOUND")
    assert await client.file_markdown("p", "d") == (None, "ROUTE_ABSENTE")  # OpenRAG plus ancien
