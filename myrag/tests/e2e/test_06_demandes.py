"""Demandes de la communauté : dire ce qui manque, soutenir, lire l'avancement, clore.

La demande d'essai est close par l'API à la fin (l'auteur en a le droit) : rien ne reste
en vue des autres testeurs, l'accueil ne la mettra pas « en ce moment ».
"""
from __future__ import annotations

import re

import pytest

from tests.e2e.conftest import _liste

TITRE = "E2E, à ignorer : jeu d'essai de la suite de tests"


@pytest.fixture(scope="module")
def capacite_demandes(session_testeur):
    config = session_testeur.get("/api/config").json()
    if config.get("demandes") is not True:
        pytest.skip("la capacité « demandes » est éteinte sur la cible (capacites.json)")


@pytest.fixture(scope="module")
def demande_essai(session_testeur, capacite_demandes):
    """L'identifiant de la demande déposée par le parcours ; close en fin de module."""
    boite = {"id": None}
    yield boite
    if boite["id"]:
        session_testeur.post(f"/api/demandes/{boite['id']}/clore",
                             {"motif": "Demande d'essai de la suite de tests : close automatiquement."})


def test_la_page_explique_le_seuil_et_le_garant(session_testeur, capacite_demandes, captures):
    page = session_testeur.aller("/demandes")
    assert "Demandes de la communauté" in page.locator("h1").first.inner_text()
    texte = session_testeur.texte()
    assert re.search(r"garant", texte, re.I) and re.search(r"chantier", texte, re.I)
    captures.prendre(page, "08-demandes")


def test_deposer_une_demande(session_testeur, demande_essai, captures):
    page = session_testeur.aller("/demandes")
    page.get_by_role("button", name=re.compile("Demander un jeu de données")).click()
    page.locator("#d-titre").wait_for(state="visible", timeout=10_000)
    page.locator("#d-titre").fill(TITRE)
    page.locator("#d-usage").fill("Vérifier qu'une demande se dépose depuis l'interface.")
    page.locator("#d-freq").select_option(index=1)
    page.locator("#d-serv").fill("Suite de tests")
    page.locator("#d-acces").fill("Aucune : c'est une demande d'essai.")
    contact = page.locator("#d-contact")
    if contact.count() and not contact.input_value().strip():
        contact.fill("suite-de-tests@fake-domain.name")
    captures.prendre(page, "08-demande-formulaire", mobile=False)
    page.get_by_role("button", name="Déposer la demande").click()
    page.wait_for_timeout(2_000)
    assert "déposée" in session_testeur.texte(), "pas de confirmation de dépôt"
    captures.prendre(page, "08-demande-deposee", mobile=False)
    demandes = _liste(session_testeur.get("/api/demandes").json(), "demandes")
    mienne = next((d for d in demandes if d.get("titre") == TITRE), None)
    assert mienne, "la demande déposée n'est pas dans la liste"
    demande_essai["id"] = mienne.get("id") or mienne.get("ident")


def test_la_demande_se_lit_et_dit_ce_qui_manque(session_testeur, demande_essai, captures):
    assert demande_essai["id"], "pas de demande déposée"
    page = session_testeur.aller(f"/demandes/{demande_essai['id']}")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    assert TITRE in page.locator("h1").first.inner_text()
    texte = session_testeur.texte()
    assert re.search(r"il manque|soutien", texte, re.I), "la page ne dit pas ce qui manque pour avancer"
    captures.prendre(page, "08-demande-detail")


def test_soutenir_puis_retirer_son_soutien(session_testeur, demande_essai):
    page = session_testeur.aller(f"/demandes/{demande_essai['id']}")
    bouton = page.get_by_role("button", name=re.compile(r"^(Moi aussi|Retirer mon soutien)$")).first
    bouton.wait_for(state="visible", timeout=30_000)
    if "Moi aussi" in bouton.inner_text():
        bouton.click()
        page.wait_for_timeout(1_500)
        assert page.get_by_role("button", name="Retirer mon soutien").count() == 1
    page.get_by_role("button", name="Retirer mon soutien").click()
    page.wait_for_timeout(1_500)
    assert page.get_by_role("button", name="Moi aussi").count() == 1


def test_l_auteur_peut_clore_sa_demande_depuis_la_page(session_testeur, demande_essai):
    """L'API l'autorise (auteur, garant ou administration) ; la page doit l'offrir."""
    page = session_testeur.aller(f"/demandes/{demande_essai['id']}")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    assert page.get_by_role("button", name=re.compile(r"^Clore")).count() == 1, "« Clore… » doit être offert à l'auteur"
