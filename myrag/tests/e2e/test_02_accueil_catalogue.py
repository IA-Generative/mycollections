"""Ce qu'un nouveau venu voit en premier : l'accueil dit quoi faire, le catalogue liste ce qui
existe, une fiche de collection se lit, et une adresse inconnue est dite en français."""
from __future__ import annotations

import re

import pytest


def test_l_accueil_dit_quoi_faire(session_testeur, captures):
    page = session_testeur.aller("/")
    assert page.locator("h1").first.inner_text().strip() == "Mes collections"
    texte = session_testeur.texte()
    assert "Que souhaitez-vous faire" in texte
    for bloc in ("Découvrir", "Explorer le catalogue", "Créer une collection"):
        assert bloc in texte, f"le bloc « {bloc} » manque à l'accueil"
    assert "Il vous manque une donnée pour travailler" in texte
    captures.prendre(page, "02-accueil")


def test_l_exemple_de_l_accueil_ouvre_le_bac_a_sable_prerempli(session_testeur, collection_publiee, captures):
    """« Poser cette question » mène au bac à sable de la collection, la question déjà écrite."""
    page = session_testeur.aller("/")
    bouton = page.get_by_role("link", name=re.compile("Poser cette question"))
    assert bouton.count() == 1, "l'accueil n'offre pas « Poser cette question »"
    bouton.click()
    page.wait_for_url(re.compile(r"/c/[^/]+/playground"), timeout=30_000)
    page.locator("#question").wait_for(state="visible", timeout=30_000)
    assert page.locator("#question").input_value().strip(), "la question n'est pas préremplie"
    captures.prendre(page, "02-accueil-vers-bac-a-sable")


def test_le_catalogue_liste_les_collections(session_testeur, collection_publiee, captures):
    page = session_testeur.aller("/admin/catalog")
    assert "Catalogue des collections existantes" in page.locator("h1").first.inner_text()
    lignes = page.locator("tbody tr")
    lignes.first.wait_for(state="visible", timeout=30_000)
    assert lignes.count() >= 1
    liens = page.locator("tbody tr a.fr-link[href^='/c/']")
    assert liens.count() >= 1, "aucune collection cliquable dans le catalogue"
    assert page.locator(f"a[href='/c/{collection_publiee['name']}']").count() >= 1, \
        "la collection publiée de l'accueil n'est pas dans le catalogue"
    captures.prendre(page, "02-catalogue")


def test_la_recherche_du_catalogue_filtre(session_testeur, collection_publiee):
    page = session_testeur.aller("/admin/catalog")
    page.locator("tbody tr").first.wait_for(state="visible", timeout=30_000)
    avant = page.locator("tbody tr").count()
    mot = (collection_publiee.get("titre") or collection_publiee["name"]).split()[0]
    page.locator(".fr-search-bar input").fill(mot)
    page.wait_for_timeout(600)
    apres = page.locator("tbody tr").count()
    assert 1 <= apres <= avant
    page.locator(".fr-search-bar input").fill("zzzz-rien-ne-correspond")
    page.wait_for_timeout(600)
    assert "Aucune collection" in session_testeur.texte() or page.locator("tbody tr").count() == 0


def test_un_lecteur_ne_voit_pas_les_gestes_d_administration_du_catalogue(session_testeur):
    """Archiver et Purger sont des gestes de gestion : un simple lecteur ne doit pas les voir."""
    if any(g.endswith("/superadmin") for g in session_testeur.groupes()):
        pytest.skip("le compte testeur est superadmin : le constat ne se joue qu'avec un lecteur")
    page = session_testeur.aller("/admin/catalog")
    page.locator("tbody tr").first.wait_for(state="visible", timeout=30_000)
    archiver = page.get_by_role("button", name=re.compile(r"^(Archiver|Purger|Désarchiver)$")).count()
    if archiver:
        pytest.xfail("P0 ergonomie : « Archiver / Purger » sont offerts à tout lecteur du catalogue (catalog.vue) ; l'API refuse ensuite, mais le bouton promet")
    assert archiver == 0


def test_la_fiche_d_une_collection_se_lit(session_testeur, collection_publiee, captures):
    page = session_testeur.aller(f"/c/{collection_publiee['name']}")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    titre = page.locator("h1").first.inner_text().strip()
    assert titre and "sans configuration" not in titre
    onglets = page.get_by_role("tab")
    assert onglets.count() >= 3, "la fiche n'a pas d'onglets"
    libelles = [onglets.nth(i).inner_text().strip() for i in range(onglets.count())]
    assert any("Consulter" in l for l in libelles), libelles
    assert any("Documents" in l for l in libelles), libelles
    captures.prendre(page, "03-fiche-collection")

    page.get_by_role("tab", name=re.compile("Documents")).click()
    page.wait_for_timeout(1_500)
    panneau = page.get_by_role("tabpanel")
    assert panneau.count() >= 1 and panneau.first.is_visible()
    captures.prendre(page, "03-fiche-documents", mobile=False)


@pytest.mark.xfail(strict=True, reason="P1 : aucune page d'erreur de l'application (error.vue) : une adresse inconnue montre la page par défaut de Nuxt, en anglais")
def test_une_adresse_inconnue_est_dite_en_francais(session_testeur, captures):
    page = session_testeur.aller("/cette-page-n-existe-pas")
    page.wait_for_timeout(1_500)
    texte = session_testeur.texte()
    captures.prendre(page, "02-page-inconnue", mobile=False)
    assert re.search(r"introuvable|n'existe pas|page inconnue", texte, re.I), texte[:200]
