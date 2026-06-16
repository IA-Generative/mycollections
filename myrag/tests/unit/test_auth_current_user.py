"""Tests de la dépendance d'identification current_user (groupes, username)."""

import pytest

import app.config
from app.auth import current_user


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(app.config.settings, "auth_enabled", True)


def test_auth_disabled_returns_synthetic_superadmin(monkeypatch):
    monkeypatch.setattr(app.config.settings, "auth_enabled", False)
    u = current_user(claims={})
    # Comportement dev/tests préservé : tout visible.
    assert any(g.endswith("/superadmin") for g in u.groups)


def test_parses_sub_username_and_groups(auth_on):
    u = current_user(claims={
        "sub": "abc-123",
        "preferred_username": "alice",
        "groups": ["/myrag/collec-a", "/myrag/collec-a-admin"],
    })
    assert u.sub == "abc-123"
    assert u.username == "alice"
    assert u.groups == ["/myrag/collec-a", "/myrag/collec-a-admin"]


def test_missing_groups_yields_empty(auth_on):
    u = current_user(claims={"sub": "x"})
    assert u.groups == []


def test_non_list_groups_yields_empty(auth_on):
    u = current_user(claims={"groups": "pas-une-liste"})
    assert u.groups == []


def test_non_string_group_entries_filtered(auth_on):
    u = current_user(claims={"groups": ["/myrag/x", 123, None, "/myrag/y"]})
    assert u.groups == ["/myrag/x", "/myrag/y"]


def test_username_falls_back_to_email(auth_on):
    u = current_user(claims={"email": "a@b.gouv.fr"})
    assert u.username == "a@b.gouv.fr"
