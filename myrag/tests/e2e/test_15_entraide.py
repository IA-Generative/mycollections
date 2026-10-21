"""Le réseau d'entraide : lancer un appel (brouillon), le lire. Ignoré si le drapeau `entraide`
est éteint sur la cible. L'appel d'essai est clos par l'API à la fin : rien ne reste en vue."""

from __future__ import annotations

import pytest

TITRE = "E2E, à ignorer : appel d'essai de la suite de tests"


@pytest.fixture(scope="module")
def capacite_entraide(session_testeur):
    config = session_testeur.get("/api/config").json()
    if config.get("entraide") is not True:
        pytest.skip("la capacité « entraide » est éteinte sur la cible (capacites.json)")


def test_la_page_entraide_se_lit(session_testeur, capacite_entraide, captures):
    page = session_testeur.aller("/entraide")
    assert page.locator("h1").first.inner_text().startswith("Entraide")
    assert "Lancer un appel" in session_testeur.texte()


def test_lancer_puis_clore_un_appel(session_testeur, capacite_entraide):
    page = session_testeur.aller("/entraide/nouveau")
    page.get_by_label("Titre de l'appel").press_sequentially(TITRE)
    page.get_by_role("button", name="Enregistrer le brouillon").click()
    page.wait_for_url("**/entraide/*")
    assert TITRE in session_testeur.texte()
    ident = page.url.rstrip("/").split("/")[-1]
    session_testeur.post(f"/api/entraide/appels/{ident}/clore", {})
