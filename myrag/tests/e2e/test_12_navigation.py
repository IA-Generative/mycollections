"""La navigation sous drapeaux (ADR-0003, lot 0) : le menu affiché est celui que les capacités
du serveur annoncent — drapeaux faux, exactement le menu d'avant le chantier ; une page sous
drapeau faux est une 404 en français ; drapeau vrai, ses pages et son sous-menu existent.

La règle attendue est recopiée de `frontend/utils/navigation.ts` (testée par Vitest) : la changer
là, c'est la changer ici."""

from __future__ import annotations

import re


def _attendues(capacites: dict, admin: bool) -> list[str]:
    entrees = ["Accueil"]
    if capacites.get("assistants") is True:
        entrees.append("Assistants")
    entrees.append("Catalogue")
    if capacites.get("entraide") is True:
        entrees.append("Réseau d'entraide")
    elif capacites.get("demandes") is True:
        entrees.append("Demandes de la communauté")
    entrees.append("Soyez acteurs vous-mêmes")
    if admin:
        entrees.append("Administration")
    return entrees


def _capacites(session) -> dict:
    r = session.get("/api/config")
    assert r.status == 200, r.status
    return r.json()


def test_le_menu_est_celui_que_les_capacites_annoncent(session_testeur, captures):
    capacites = _capacites(session_testeur)
    page = session_testeur.aller("/")
    page.locator("nav.fr-nav .fr-nav__link").first.wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(1_000)
    liens = [t.strip() for t in page.locator("nav.fr-nav > ul > li > a.fr-nav__link").all_inner_texts()]
    assert liens == _attendues(capacites, session_testeur.superadmin()), liens
    assert page.locator("nav.fr-nav a[aria-current=page]").all_inner_texts() == ["Accueil"]
    captures.prendre(page, "12-menu", mobile=False)


def test_une_page_sous_drapeau_faux_est_introuvable_sinon_elle_s_ouvre(session_testeur):
    capacites = _capacites(session_testeur)
    for drapeau, chemin, titre in (("assistants", "/assistants", "Assistants"), ("entraide", "/entraide", "Réseau d'entraide")):
        page = session_testeur.aller(chemin)
        page.wait_for_timeout(1_500)
        if capacites.get(drapeau) is True:
            assert page.locator("h1").first.inner_text().strip() == titre
        else:
            assert re.search(r"introuvable|n'existe pas", session_testeur.texte(), re.I), chemin


def test_les_rubriques_d_un_assistant(session_testeur):
    if _capacites(session_testeur).get("assistants") is not True:
        import pytest

        pytest.skip("drapeau assistants à faux sur cette cible")
    page = session_testeur.aller("/assistants/exemple-e2e")
    page.wait_for_url(re.compile(r"/assistants/exemple-e2e/sources$"), timeout=15_000)
    rubriques = page.locator("nav[aria-label^='Rubriques'] a").all_inner_texts()
    assert [r.strip() for r in rubriques] == ["Sources", "Consignes", "Réponses fiables", "Qualité", "Publication", "Bac à sable"]
    page.locator("nav[aria-label^='Rubriques'] a", has_text="Consignes").click()
    page.wait_for_url(re.compile(r"/consignes$"), timeout=15_000)
    assert page.locator("nav[aria-label^='Rubriques'] a[aria-current=page]").inner_text().strip() == "Consignes"
