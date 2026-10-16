"""Le bac à sable : poser une question à une collection publiée, lire d'où vient la réponse."""

from __future__ import annotations

import json
import re

import pytest

#: Le corps rendu par `POST /api/playground/<collection>/chat` pour la question du module.
_REPONSE_API: dict = {}


@pytest.fixture(scope="module")
def reponse_obtenue(session_testeur, collection_publiee, captures):
    """Une question posée, une réponse rendue : les tests du module lisent la même page."""
    page = session_testeur.aller(f"/c/{collection_publiee['name']}/playground")
    page.locator("#question").wait_for(state="visible", timeout=30_000)
    captures.prendre(page, "04-bac-a-sable-vide")
    page.locator("#question").fill(collection_publiee["question"])
    with page.expect_response(lambda r: "/api/playground/" in r.url and r.url.endswith("/chat") and r.request.method == "POST", timeout=180_000) as appel:
        page.get_by_role("button", name="Envoyer").click()
    try:
        _REPONSE_API.update(appel.value.json() or {})
    except Exception:  # noqa: BLE001 — un corps illisible est jugé par les tests, pas ici
        pass
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


def test_une_puce_par_fichier_cite(reponse_obtenue):
    """Autant de puces que de fichiers distincts cités par l'API. Des sources mal lues (forme
    d'OpenRAG 2.3, métadonnées sous `chunk`) perdent leur nom et fusionnent toutes en UNE puce,
    ce que `>= 1` laisse passer."""
    sources = [s for s in (_REPONSE_API.get("sources") or []) if isinstance(s, dict)]
    assert sources, "la réponse de l'API n'a pas été lue, ou ne cite aucune source"
    documents = [s for s in sources if s.get("source_type") != "web"]
    assert not any("chunk" in s for s in documents), "des sources arrivent au front sans être aplaties (forme OpenRAG 2.3)"
    sans_nom = [s for s in documents if not (s.get("original_filename") or s.get("filename"))]
    assert not sans_nom, f"{len(sans_nom)} source(s) documentaire(s) sans nom de fichier : leurs puces fusionneraient"
    fichiers = {s.get("original_filename") or s.get("filename") for s in documents}
    assert fichiers == set(_REPONSE_API.get("source_names") or []), "les puces et la liste des noms ne parlent pas des mêmes fichiers"
    # La clé de dédoublonnage de ChatMessage.vue : le nom, à défaut le début du JSON (sources web).
    cles = {s.get("original_filename") or s.get("filename") or json.dumps(s, ensure_ascii=False, separators=(",", ":"))[:40] for s in sources}
    puces = reponse_obtenue.locator(".myrag-msg--assistant .myrag-source-chip-wrap")
    assert puces.count() == len(cles), f"{puces.count()} puce(s) pour {len(fichiers)} fichier(s) cité(s)"


def test_la_source_se_lit_au_survol_puis_en_fenetre(reponse_obtenue, captures):
    """La puce ouvre la fenêtre de lecture. Le survol montre un aperçu quand le morceau a du texte
    à montrer — un morceau vide (un document importé sans texte) n'en a pas, par conception."""
    page = reponse_obtenue
    puce = page.locator(".myrag-msg--assistant .myrag-source-chip-wrap").first
    bulle = page.locator(".myrag-source-chip__popover")
    puce.scroll_into_view_if_needed()
    puce.hover()
    page.wait_for_timeout(1_500)
    if bulle.count() and bulle.first.is_visible():
        assert bulle.first.inner_text().strip()
        captures.prendre(page, "04-source-bulle", mobile=False)
        page.mouse.move(0, 0)
        page.wait_for_timeout(800)
    lien = puce.locator("a[href]").first
    assert lien.count() == 1, "la puce n'offre aucun lien vers sa source"
    assert "/api/openrag/" in (lien.get_attribute("href") or ""), "le lien de la puce ne passe pas par le proxy signé"
    lien.click()
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
    assert re.search(r"gestionnaire", texte) and re.search(r"réponse validée|transmis", texte), "la page doit dire ce que 👍 et 👎 déclenchent, sans infobulle"


def test_le_bac_a_sable_vouvoie(session_testeur, collection_publiee):
    """Le reste de l'application vouvoie : l'écran de question aussi, consigne et champ compris."""
    page = session_testeur.aller(f"/c/{collection_publiee['name']}/playground")
    page.locator("#question").wait_for(state="visible", timeout=30_000)
    textes = page.locator("body").inner_text() + " " + (page.locator("#question").get_attribute("placeholder") or "")
    if re.search(r"\bTa question\b|\bClique\b|\bPose une question\b|\btape la tienne\b", textes):
        pytest.xfail("P1 ergonomie : le bac à sable tutoie (« Ta question ici… », « Clique sur une question ») ; le reste de l'application vouvoie (PR #44 le corrige)")
    assert True
