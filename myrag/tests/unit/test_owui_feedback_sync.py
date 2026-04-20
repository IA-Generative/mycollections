"""Unit tests for the OWUI → MyRAG feedback sync.

Focus on the parsing logic (message extraction, collection-from-model,
rating coercion) — the database roundtrip is exercised separately by the
integration path when the CronJob runs.
"""

from __future__ import annotations

from app.services.owui_feedback_sync import (
    _collection_from_model,
    _extract_qa,
)


class TestCollectionFromModel:
    def test_openrag_prefix(self):
        assert _collection_from_model("openrag-ceseda") == "ceseda"

    def test_multi_dash_collection(self):
        # The trailing part is the literal partition name, dashes preserved.
        assert _collection_from_model("openrag-my-complex-col") == "my-complex-col"

    def test_non_openrag_returns_none(self):
        assert _collection_from_model("gpt-4") is None
        assert _collection_from_model("mistral-instruct") is None

    def test_empty_returns_none(self):
        assert _collection_from_model("") is None
        assert _collection_from_model(None) is None  # type: ignore[arg-type]


class TestExtractQA:
    def test_returns_question_and_answer_from_history_map(self):
        chat = {
            "history": {
                "messages": {
                    "q1": {"role": "user", "content": "Quelle est la capitale ?", "childrenIds": ["a1"]},
                    "a1": {"role": "assistant", "content": "Paris.", "parentId": "q1"},
                }
            }
        }
        q, a = _extract_qa(chat, "a1")
        assert q == "Quelle est la capitale ?"
        assert a == "Paris."

    def test_missing_parent_yields_empty_question(self):
        chat = {
            "history": {
                "messages": {
                    "a1": {"role": "assistant", "content": "Solo reply."},
                }
            }
        }
        q, a = _extract_qa(chat, "a1")
        assert q == ""
        assert a == "Solo reply."

    def test_unknown_message_id_yields_blanks(self):
        chat = {"history": {"messages": {"other": {"content": "nope"}}}}
        q, a = _extract_qa(chat, "missing-id")
        assert q == ""
        assert a == ""

    def test_malformed_chat_blob_does_not_crash(self):
        # Real-world safety: if OWUI changes the blob shape, we want the
        # sync to skip the row, not abort the batch.
        q, a = _extract_qa({"weird": "shape"}, "anything")
        assert (q, a) == ("", "")
        q, a = _extract_qa(None, "anything")
        assert (q, a) == ("", "")
