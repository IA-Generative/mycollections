"""Tests de la dépendance d'identification current_user (groupes, username, identité)."""

import asyncio

import pytest

import app.auth as auth_module
import app.config
from app.auth import CurrentUser, current_user


def appel(**kwargs) -> CurrentUser:
    """current_user est asynchrone (elle peut interroger /userinfo) ; les tests
    l'appellent par ce raccourci plutôt que de se déclarer tous asynchrones."""
    kwargs.setdefault("credentials", None)
    return asyncio.run(current_user(**kwargs))


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(app.config.settings, "auth_enabled", True)


def test_auth_disabled_returns_synthetic_superadmin(monkeypatch):
    monkeypatch.setattr(app.config.settings, "auth_enabled", False)
    u = appel(claims={})
    # Comportement dev/tests préservé : tout visible.
    assert any(g.endswith("/superadmin") for g in u.groups)


def test_parses_sub_username_and_groups(auth_on):
    u = appel(claims={
        "sub": "abc-123",
        "preferred_username": "alice",
        "groups": ["/myrag/collec-a", "/myrag/collec-a-admin"],
    })
    assert u.sub == "abc-123"
    assert u.username == "alice"
    assert u.groups == ["/myrag/collec-a", "/myrag/collec-a-admin"]


def test_missing_groups_yields_empty(auth_on):
    u = appel(claims={"sub": "x"})
    assert u.groups == []


def test_non_list_groups_yields_empty(auth_on):
    u = appel(claims={"groups": "pas-une-liste"})
    assert u.groups == []


def test_non_string_group_entries_filtered(auth_on):
    u = appel(claims={"groups": ["/myrag/x", 123, None, "/myrag/y"]})
    assert u.groups == ["/myrag/x", "/myrag/y"]


def test_username_falls_back_to_email(auth_on):
    u = appel(claims={"email": "a@b.gouv.fr"})
    assert u.username == "a@b.gouv.fr"


# --- Identité résolue par /userinfo quand le jeton d'accès ne la porte pas ---------

class _Jetons:
    """Substitut de credentials HTTPBearer."""

    def __init__(self, jeton: str):
        self.credentials = jeton


def test_sub_absent_est_demande_a_userinfo(auth_on, monkeypatch):
    vus = []

    async def faux_userinfo(jeton):
        vus.append(jeton)
        return "sub-du-fournisseur"

    monkeypatch.setattr(auth_module, "_sub_depuis_userinfo", faux_userinfo)
    u = appel(claims={"email": "a@b.gouv.fr"}, credentials=_Jetons("jeton-brut"))
    assert u.sub == "sub-du-fournisseur"
    assert vus == ["jeton-brut"]


def test_sub_present_ne_declenche_aucun_appel(auth_on, monkeypatch):
    async def interdit(jeton):  # pragma: no cover — ne doit jamais être appelée
        raise AssertionError("/userinfo interrogé alors que le jeton porte déjà `sub`")

    monkeypatch.setattr(auth_module, "_sub_depuis_userinfo", interdit)
    assert appel(claims={"sub": "deja-la"}, credentials=_Jetons("x")).sub == "deja-la"


def test_userinfo_muet_donne_une_identite_vide(auth_on, monkeypatch):
    async def rien(jeton):
        return None

    monkeypatch.setattr(auth_module, "_sub_depuis_userinfo", rien)
    assert appel(claims={}, credentials=_Jetons("x")).sub == ""
