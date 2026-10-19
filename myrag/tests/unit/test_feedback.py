"""Tests for feedback system (TDD)."""

from __future__ import annotations

import pytest

from app.services.feedback_service import FeedbackService


@pytest.fixture
def svc(tmp_path):
    return FeedbackService(data_dir=str(tmp_path))


class TestFeedback:
    def test_ingest(self, svc):
        svc.ingest("col", "Q1?", "Response1", rating=1, user_id="eric")
        items = svc.lister("col")
        assert len(items) == 1
        assert items[0].rating == 1

    def test_ingest_negative(self, svc):
        svc.ingest("col", "Q1?", "Bad response", rating=-1, reason="Incorrect")
        items = svc.lister("col")
        assert items[0].rating == -1
        assert items[0].reason == "Incorrect"

    def test_idempotent(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=1, owui_message_id="msg-1")
        svc.ingest("col", "Q1?", "R1", rating=-1, owui_message_id="msg-1")
        items = svc.lister("col")
        assert len(items) == 1  # deduplicated
        assert items[0].rating == -1  # updated

    def test_list_filter_status(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=-1)
        svc.ingest("col", "Q2?", "R2", rating=1)
        pending = svc.lister("col", status="pending")
        assert len(pending) == 2

    def test_review(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=-1)
        items = svc.lister("col")
        svc.review(items[0].id, "col", status="reviewed", reviewed_by="admin")
        updated = svc.get("col", items[0].id)
        assert updated.status == "reviewed"

    def test_promote_to_qr(self, svc):
        svc.ingest("col", "Q1?", "Bad answer", rating=-1)
        items = svc.lister("col")
        svc.promote(items[0].id, "col", promote_to="qr")
        updated = svc.get("col", items[0].id)
        assert updated.status == "promoted"
        assert updated.promoted_to == "qr"

    def test_promote_to_eval(self, svc):
        svc.ingest("col", "Q1?", "Bad answer", rating=-1)
        items = svc.lister("col")
        svc.promote(items[0].id, "col", promote_to="eval")
        updated = svc.get("col", items[0].id)
        assert updated.promoted_to == "eval"

    def test_ignore(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=-1)
        items = svc.lister("col")
        svc.review(items[0].id, "col", status="ignored")
        updated = svc.get("col", items[0].id)
        assert updated.status == "ignored"

    def test_stats(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=1)
        svc.ingest("col", "Q2?", "R2", rating=1)
        svc.ingest("col", "Q3?", "R3", rating=-1)
        stats = svc.stats("col")
        assert stats["total"] == 3
        assert stats["positive"] == 2
        assert stats["negative"] == 1
        assert stats["satisfaction_rate"] == pytest.approx(0.667, abs=0.01)
        assert stats["pending_review"] == 3

    def test_persistence(self, svc, tmp_path):
        svc.ingest("col", "Q1?", "R1", rating=1)
        svc2 = FeedbackService(data_dir=str(tmp_path))
        assert len(svc2.lister("col")) == 1


# --- Les derniers avis d'une collection (fiche d'une collection, ?limit=N) ---


def _avis(client, en_tant_que, nom, n):
    from tests.conftest import personne

    en_tant_que(personne("lecteur-avis"))
    for i in range(n):
        r = client.post("/api/feedback/ingest", json={"collection": nom, "question": f"Question {i} ?", "response": "Réponse.", "rating": 1 if i % 2 else -1})
        assert r.status_code == 200, r.text


def test_limit_rend_les_plus_recents_d_abord(client, en_tant_que, creer_collection, nom):
    from tests.conftest import personne

    createur = personne("createur-avis")
    creer_collection(nom, createur)
    _avis(client, en_tant_que, nom, 5)
    en_tant_que(createur)
    r = client.get(f"/api/feedback/{nom}", params={"limit": 3})
    assert r.status_code == 200, r.text
    questions = [f["question"] for f in r.json()["feedback"]]
    assert questions == ["Question 4 ?", "Question 3 ?", "Question 2 ?"]
    assert len(client.get(f"/api/feedback/{nom}").json()["feedback"]) == 5  # sans limit : tout


@pytest.mark.parametrize("limit", [0, 51, -1])
def test_limit_hors_bornes_est_refuse(client, en_tant_que, creer_collection, nom, limit):
    from tests.conftest import personne

    createur = personne("createur-bornes")
    creer_collection(nom, createur)
    en_tant_que(createur)
    assert client.get(f"/api/feedback/{nom}", params={"limit": limit}).status_code == 422


def test_les_derniers_avis_restent_reserves_a_qui_gere(client, en_tant_que, creer_collection, nom):
    from tests.conftest import personne

    creer_collection(nom, personne("createur-reserve"))
    _avis(client, en_tant_que, nom, 1)
    en_tant_que(personne("simple-lecteur"))
    assert client.get(f"/api/feedback/{nom}", params={"limit": 3}).status_code == 403
