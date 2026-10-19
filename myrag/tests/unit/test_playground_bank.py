"""Tests for GET /api/playground/{col}/bank — the aggregated question bank.

Hits the real DB configured by DATABASE_URL (SQLite in dev). Each test cleans
the collection it touched. QRCache is stubbed to tmp_path so we don't pollute
the dev data dir.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def collection_name(request):
    name = f"pytest-bank-{request.node.name}"[:60]

    async def _purge():
        import sqlite3

        from app.config import settings

        if "sqlite" in settings.database_url:
            db_path = settings.database_url.split("///")[-1]
            try:
                conn = sqlite3.connect(db_path)
                for t in ("eval_datasets", "feedback", "paire_qa"):
                    conn.execute(f"DELETE FROM {t} WHERE collection_name = ?", (name,))
                conn.commit()
                conn.close()
            except Exception:
                pass

    yield name
    asyncio.run(_purge())


@pytest.fixture
def qr_cache_tmp(tmp_path, monkeypatch):
    """Redirect QRCache to a tmp dir so tests don't leak into dev data."""
    from app.services import qr_cache as qr_mod

    original_init = qr_mod.QRCache.__init__

    def patched_init(self, data_dir=None):
        original_init(self, data_dir=str(tmp_path))

    monkeypatch.setattr(qr_mod.QRCache, "__init__", patched_init)
    yield tmp_path


class TestBankEmpty:
    def test_empty_bank_returns_zero_stats(self, client, collection_name, qr_cache_tmp):
        resp = client.get(f"/api/playground/{collection_name}/bank")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["stats"] == {
            "total": 0,
            "generated": 0,
            "imported": 0,
            "fb_neg": 0,
            "promoted": 0,
        }


class TestBankAggregation:
    @pytest.mark.asyncio
    async def test_aggregates_all_four_sources(
        self,
        client,
        collection_name,
        qr_cache_tmp,
    ):
        from app.database import async_session
        from app.models.db import Feedback
        from app.services import questions_store as qs

        # 1. Le jeu de questions : deux générées, une importée, une validée avec réponse fiable,
        #    une rejetée (qui ne s'affiche pas).
        await qs.importer_questions(
            collection_name, [{"question": "Question auto 1 ?", "expected_answer": "A1"}, {"question": "Question auto 2 ?", "expected_answer": "A2"}], None, origine="generee"
        )
        await qs.importer_questions(collection_name, [{"question": "Question importee ?", "expected_answer": "AI"}], None)
        fiable = await qs.creer_question(collection_name, {"question": "Promu question ?", "reponse": "Bonne reponse", "relecture": "valide"}, None)
        await qs.modifier_question(collection_name, fiable.id, {"fiable": True}, None)
        rejet = await qs.creer_question(collection_name, {"question": "Mauvaise question ?", "reponse": "x"}, None)
        await qs.modifier_question(collection_name, rejet.id, {"relecture": "rejete"}, None)
        # 2. Un avis négatif pas encore traité, et un avis promu (devenu question : absent du lot fb_neg).
        async with async_session() as session:
            session.add_all(
                [
                    Feedback(
                        collection_name=collection_name,
                        question="Ca a mal repondu ?",
                        response="Mauvaise reponse",
                        rating=-1,
                        reason="trop vague",
                        owui_chat_id="chat-1",
                        status="pending",
                    ),
                    Feedback(collection_name=collection_name, question="Deja traite ?", response="x", rating=-1, status="promoted"),
                ]
            )
            await session.commit()

        resp = client.get(f"/api/playground/{collection_name}/bank")
        assert resp.status_code == 200
        body = resp.json()
        stats = body["stats"]
        assert stats == {"total": 5, "generated": 2, "imported": 1, "fb_neg": 1, "promoted": 1}, stats
        par_source = {item["source"]: item for item in body["items"]}
        assert par_source["promoted"]["metadata"]["fiable"] is True
        assert par_source["generated"]["expected_answer"] in ("A1", "A2")
        assert par_source["generated"]["id"].startswith("q_")

    @pytest.mark.asyncio
    async def test_positive_feedback_excluded_from_fb_neg(
        self,
        client,
        collection_name,
        qr_cache_tmp,
    ):
        """Only rating < 0 should land in the fb_neg bucket."""
        from app.database import async_session
        from app.models.db import Feedback

        async with async_session() as session:
            session.add_all(
                [
                    Feedback(collection_name=collection_name, question="OK?", response="Good", rating=1, status="pending"),
                    Feedback(collection_name=collection_name, question="Bad?", response="Wrong", rating=-1, status="pending"),
                ]
            )
            await session.commit()

        resp = client.get(f"/api/playground/{collection_name}/bank")
        body = resp.json()
        assert body["stats"]["fb_neg"] == 1
        assert body["stats"]["total"] == 1

    @pytest.mark.asyncio
    async def test_other_collection_not_leaked(
        self,
        client,
        collection_name,
        qr_cache_tmp,
    ):
        """The bank is strictly scoped to one collection."""
        from app.database import async_session
        from app.models.db import Feedback

        other = f"{collection_name}-other"
        async with async_session() as session:
            session.add(Feedback(collection_name=other, question="Q?", response="R", rating=-1, status="pending"))
            await session.commit()

        try:
            resp = client.get(f"/api/playground/{collection_name}/bank")
            assert resp.json()["stats"]["total"] == 0
        finally:
            # Cleanup the sibling row
            import sqlite3

            from app.config import settings

            if "sqlite" in settings.database_url:
                db_path = settings.database_url.split("///")[-1]
                conn = sqlite3.connect(db_path)
                conn.execute("DELETE FROM feedback WHERE collection_name = ?", (other,))
                conn.commit()
                conn.close()
