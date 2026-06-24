"""Tests pour POST /api/playground/{collection}/generate-eval (Bug 2).

Vérouille le correctif : quand l'endpoint de contenu par fichier d'OpenRAG
(get_file_content) renvoie du vide — limitation connue (cf. commit b2d714a) —
la génération ne doit PLUS répondre 400, mais se rabattre sur le RAG chat
(OpenRAG auto-récupère depuis la partition). Le 400 « collection vide » reste
seulement quand il n'y a aucun fichier indexé.
"""

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _mock_client(mock_cls, *, files, file_content="", chat_json=None):
    m = mock_cls.return_value
    m.health_check = AsyncMock(return_value=True)
    m.list_files = AsyncMock(return_value=files)
    m.get_file_content = AsyncMock(return_value=file_content)
    content = json.dumps(chat_json) if chat_json is not None else ""
    m.chat = AsyncMock(return_value={"choices": [{"message": {"content": content}}]})
    return m


@patch("app.routers.playground.OpenRAGClient")
def test_fallback_chat_quand_contenu_illisible(mock_cls):
    from app.main import app

    chat_json = {
        "name": "victor2-evaluation",
        "description": "d",
        "questions": [
            {"id": "q1", "question": "De quoi parle la collection ?",
             "expected_answer": "A", "must_cite": [], "tags": ["theme"]},
        ],
    }
    m = _mock_client(
        mock_cls,
        files=[{"file_id": "f1"}, {"file_id": "f2"}],
        file_content="",  # contenu illisible -> déclenche le fallback
        chat_json=chat_json,
    )

    with TestClient(app) as client:
        resp = client.post("/api/playground/victor2/generate-eval")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Les questions du chat sont présentes...
    assert any(q["id"] == "q1" for q in data["questions"])
    # ...complétées par les questions hors-sujet ajoutées par l'endpoint.
    assert any(q.get("out_of_scope") for q in data["questions"])
    # Le fallback a bien utilisé le chat malgré un contenu fichier vide.
    m.chat.assert_awaited()


@patch("app.routers.playground.OpenRAGClient")
def test_400_seulement_si_collection_vide(mock_cls):
    from app.main import app

    m = _mock_client(mock_cls, files=[], chat_json=None)

    with TestClient(app) as client:
        resp = client.post("/api/playground/vide/generate-eval")

    assert resp.status_code == 400
    assert "vide" in resp.json()["detail"].lower()
    m.chat.assert_not_awaited()
