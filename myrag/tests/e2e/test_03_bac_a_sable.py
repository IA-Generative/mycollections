"""Le bac à sable : poser une question à une collection publiée, lire d'où vient la réponse."""
from __future__ import annotations

import re

import pytest


@pytest.fixture(scope="module")
def reponse_obtenue(session_testeur, collection_publiee, captures):
    """Une question posée, une réponse rendue : les tests du module lisent la même page."""
    page = session_testeur.aller(f"/c/{collection_publiee['name']}/playground")
    page.locator("#question").wait_for(state="visible", timeout=30_000)
    captures.prendre(page, "04-bac-a-sable-vide")
    page.locator("#question").fill(collection_publiee["question"])
    page.get_by_role("button", name="Envoyer").click()
    page.locator(".myrag-msg--assistant").first.wait_for(state="visible", timeout=180_000)
    page.wait_for_timeout(800)
    captures.prendre(page, "04-bac-a-sable-reponse")
    return page


def test_la_question_recoit_une_reponse_sans_erreur(reponse_obtenue):
    corps = reponse_obtenue.locator(".myrag-msg--assistant .myrag-msg__body").first.inner_text()
    assert corps.strip(), "réponse vide"
    assert not re.search(r"API error|Traceback|\{\"detail\"", corps), f"erreur brute rendue : {corps[:200]}"


def test_la_reponse_cite_ses_sources(reponse_obtenue):
    puces = reponse_obtenue.locator(".myrag-msg--assistant .myrag-source-chip-wrap")
    assert puces.count() >= 1, "aucune source citée pour une question du jeu d'évaluation de la collection"


def test_la_source_se_lit_au_survol_puis_en_fenetre(reponse_obtenue, captures):
    page = reponse_obtenue
    puce = page.locator(".myrag-msg--assistant .myrag-source-chip-wrap").first
    puce.hover()
    bulle = page.locator(".myrag-source-chip__popover")
    bulle.first.wait_for(state="visible", timeout=10_000)
    assert bulle.first.inner_text().strip()
    captures.prendre(page, "04-source-bulle", mobile=False)
    page.get_by_role("link", name=re.compile("Lire l'extrait")).first.click()
    fenetre = page.locator("dialog.myrag-viewer")
    fenetre.wait_for(state="visible", timeout=30_000)
    assert fenetre.locator("#myrag-viewer-title").inner_text().strip()
    assert fenetre.get_by_role("button", name="Fermer").count() == 1
    captures.prendre(page, "04-source-fenetre", mobile=False)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    assert fenetre.count() == 0 or not fenetre.is_visible()


def test_l_avis_dit_ce_qu_il_fait(reponse_obtenue):
    """Deux boutons 👍 👎 : la personne doit lire, sans infobulle, ce que son avis déclenche."""
    texte = reponse_obtenue.locator(".myrag-msg--assistant").first.inner_text()
    assert "Cette reponse est-elle utile" in texte or "Cette réponse est-elle utile" in texte
    if not re.search(r"cache|promou|ticket|valid", texte, re.I):
        pytest.xfail("P1 ergonomie : 👍 écrit la réponse dans le cache des réponses validées et 👎 ouvre un ticket, mais la page ne le dit que dans un `title` (VoteBar.vue)")


def test_le_bac_a_sable_vouvoie(session_testeur, collection_publiee):
    """Le reste de l'application vouvoie : l'écran de question aussi, consigne et champ compris."""
    page = session_testeur.aller(f"/c/{collection_publiee['name']}/playground")
    page.locator("#question").wait_for(state="visible", timeout=30_000)
    textes = page.locator("body").inner_text() + " " + (page.locator("#question").get_attribute("placeholder") or "")
    if re.search(r"\bTa question\b|\bClique\b|\bPose une question\b|\btape la tienne\b", textes):
        pytest.xfail("P1 ergonomie : le bac à sable tutoie (« Ta question ici… », « Clique sur une question ») ; le reste de l'application vouvoie (PR #44 le corrige)")
    assert True
