"""L'accueil de la refonte ergonomique (2026-10-19) : quatre tuiles et leurs cibles, des puces de
catégorie vers le catalogue filtré, ni bandeau « merci » ni cadre « Il vous manque une donnée » ;
à 390 px, les tuiles s'empilent et le menu (dont Entraide) s'ouvre.

Les libellés attendus sont recopiés de `frontend/utils/accueil.ts` (testés par Vitest)."""

from __future__ import annotations

import re

TUILES = ("decouvrir", "explorer", "gerer", "creer")


def _capacites(session) -> dict:
    return session.get("/api/config").json()


def _titres_attendus(assistants: bool) -> list[str]:
    suffixe = " & assistants" if assistants else ""
    return [
        "Découvrir",
        "Explorer le catalogue",
        f"Suivre mes collections{suffixe}",
        "Partager une nouvelle collection" + (" & assistant" if assistants else ""),
    ]


def _tuiles(page):
    page.locator("[data-tuile]").first.wait_for(state="visible", timeout=15_000)
    return page.locator("[data-tuile]")


def test_quatre_tuiles_dans_l_ordre_et_leurs_cibles(session_testeur, captures):
    page = session_testeur.aller("/")
    assert page.locator("h1").first.inner_text().strip() == "Que souhaitez-vous faire ?"
    tuiles = _tuiles(page)
    assert [tuiles.nth(i).get_attribute("data-tuile") for i in range(tuiles.count())] == list(TUILES)
    titres = [t.strip() for t in page.locator("[data-tuile] .fr-tile__title").all_inner_texts()]
    assert titres == _titres_attendus(_capacites(session_testeur).get("assistants") is True), titres
    cibles = {cle: page.locator(f"[data-tuile={cle}] .fr-tile__link").get_attribute("href") for cle in TUILES}
    assert cibles["explorer"] == "/admin/catalog"
    assert cibles["gerer"] == "/mes-collections"
    assert cibles["creer"] == "/admin/create"
    assert re.match(r"^/(admin/catalog|c/[^/]+/playground\?q=)", cibles["decouvrir"] or ""), cibles["decouvrir"]
    captures.prendre(page, "14-accueil")


def test_ni_merci_ni_donnee_manquante(session_testeur):
    session_testeur.aller("/")
    texte = session_testeur.texte()
    assert "Il vous manque une donnée" not in texte
    assert "travaillent pour vos collègues" not in texte and "faites-les connaître" not in texte


def test_les_puces_de_categorie_menent_au_catalogue_filtre(session_testeur, collection_publiee):
    page = session_testeur.aller("/")
    puces = page.locator(".fr-tags-group a.fr-tag")
    puces.first.wait_for(state="visible", timeout=15_000)
    href = puces.first.get_attribute("href") or ""
    assert re.match(r"^/admin/catalog\?categorie=", href), href
    puces.first.click()
    page.wait_for_url(re.compile(r"/admin/catalog\?categorie="), timeout=15_000)


def test_qui_gere_voit_ce_que_ses_collections_ont_rendu_possible(session_testeur, collection_publiee):
    """Le bandeau de l'accueil donne envie de continuer : collègues aidés (au-dessus du seuil de 3,
    que le serveur applique), questions sur la fenêtre, note des usagers."""
    bilan = session_testeur.get("/api/accueil/mes-collections").json()
    page = session_testeur.aller("/")
    page.locator("[data-tuile]").first.wait_for(state="visible", timeout=15_000)
    impact = page.locator(".accueil-impact")
    if not bilan.get("collections"):
        assert impact.count() == 0, "rien à dire à qui ne gère rien"
        return
    impact.wait_for(state="visible", timeout=15_000)
    texte = impact.inner_text()
    assert f"en {bilan['fenetre_jours']} jours" in texte
    assert ("collègue" in texte and "aidé" in texte) == bool(bilan.get("personnes")), "le seuil de 3 personnes vient du serveur"


def test_a_390_px_les_tuiles_s_empilent_et_le_menu_s_ouvre(session_testeur, captures):
    page = session_testeur.page
    taille = page.viewport_size
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        session_testeur.aller("/")
        tuiles = _tuiles(page)
        boites = [tuiles.nth(i).bounding_box() for i in range(tuiles.count())]
        assert all(b for b in boites)
        xs = {round(b["x"]) for b in boites if b}
        assert len(xs) == 1, f"les tuiles ne s'empilent pas : {xs}"
        captures.prendre(page, "14-accueil-mobile", mobile=False)
        page.get_by_role("button", name=re.compile(r"^Menu$")).click()
        menu = page.locator("#menu-principal")
        menu.get_by_role("link", name="Catalogue").first.wait_for(state="visible", timeout=5_000)
        capacites = _capacites(session_testeur)
        if capacites.get("entraide") is True or capacites.get("demandes") is True:
            assert menu.get_by_role("link", name="Entraide").first.is_visible()
    finally:
        page.set_viewport_size(taille)
