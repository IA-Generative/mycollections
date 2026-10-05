"""Diagnostic d'octobre 2026, P2 : sur téléphone, aucun menu ; les fenêtres modales laissaient
le focus s'échapper ; les filtres de la banque de questions n'étaient que des emoji.
Écrits avant le correctif (ils échouent sur la 0.3.22)."""
from __future__ import annotations

import re


def test_sur_telephone_le_menu_s_ouvre_et_mene_au_catalogue(session_testeur, captures):
    page = session_testeur.page
    taille = page.viewport_size
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        session_testeur.aller("/")
        bouton = page.get_by_role("button", name=re.compile(r"^Menu$"))
        assert bouton.is_visible(), "pas de bouton « Menu » à 390 px"
        bouton.click()
        lien = page.get_by_role("link", name="Catalogue").first
        lien.wait_for(state="visible", timeout=5_000)
        captures.prendre(page, "50-menu-mobile", mobile=False)
        lien.click()
        page.wait_for_url(re.compile(r"/admin/catalog"), timeout=15_000)
        assert not page.get_by_role("button", name="Fermer").first.is_visible(), "le menu doit se refermer après navigation"
    finally:
        page.set_viewport_size(taille)


def test_la_fenetre_de_lecture_garde_le_focus(session_testeur, collection_publiee):
    page = session_testeur.aller(f"/c/{collection_publiee['name']}/playground")
    page.locator("#question").fill(collection_publiee["question"])
    page.get_by_role("button", name="Envoyer").click()
    page.locator(".myrag-msg--assistant .myrag-source-chip-wrap a[href]").first.wait_for(state="visible", timeout=180_000)
    page.locator(".myrag-msg--assistant .myrag-source-chip-wrap a[href]").first.click()
    fenetre = page.locator("dialog.myrag-viewer")
    fenetre.wait_for(state="visible", timeout=30_000)
    for _ in range(25):
        page.keyboard.press("Tab")
    dedans = page.evaluate("() => !!document.activeElement && !!document.activeElement.closest('dialog.myrag-viewer')")
    assert dedans, "le focus est sorti de la fenêtre de lecture"
    page.keyboard.press("Escape")


def test_les_filtres_de_la_banque_ont_un_nom(session_testeur, collection_publiee):
    page = session_testeur.aller(f"/c/{collection_publiee['name']}/playground")
    page.locator(".myrag-bank-filter").wait_for(state="visible", timeout=30_000)
    onglets = page.locator(".myrag-bank-filter [role=tab]")
    assert onglets.count() >= 4, "les filtres doivent être des onglets"
    for i in range(onglets.count()):
        nom = (onglets.nth(i).get_attribute("aria-label") or onglets.nth(i).inner_text()).strip()
        assert re.search(r"[A-Za-zÀ-ÿ]{3,}", nom), f"filtre sans nom lisible : {nom!r}"
