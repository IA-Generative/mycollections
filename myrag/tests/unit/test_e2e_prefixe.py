"""La suite de bout en bout tourne aussi sur une preview, qui impose le préfixe `pr-<n>-` aux
identifiants : le nom de la collection d'essai le porte (sinon la création est refusée en 422)."""

from types import SimpleNamespace

from tests.e2e.conftest import prefixe_de_la_cible


def _session(statut, corps):
    return SimpleNamespace(get=lambda chemin: SimpleNamespace(status=statut, json=lambda: corps))


def test_le_prefixe_impose_par_une_preview_est_lu():
    assert prefixe_de_la_cible(_session(200, {"prefixe_impose": "pr-84-", "max": 40})) == "pr-84-"


def test_sans_prefixe_rien():
    assert prefixe_de_la_cible(_session(200, {"prefixe_impose": ""})) == ""
    assert prefixe_de_la_cible(_session(200, {})) == ""
    assert prefixe_de_la_cible(_session(500, {"prefixe_impose": "pr-1-"})) == ""


def test_une_panne_ne_casse_pas_la_suite():
    def boum(chemin):
        raise RuntimeError("réseau")

    assert prefixe_de_la_cible(SimpleNamespace(get=boum)) == ""
