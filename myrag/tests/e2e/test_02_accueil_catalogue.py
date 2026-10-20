"""Ce qu'un nouveau venu voit en premier : l'accueil dit quoi faire, le catalogue liste ce qui
existe, une fiche de collection se lit, et une adresse inconnue est dite en français."""

from __future__ import annotations

import re


def test_l_accueil_dit_quoi_faire(session_testeur, captures):
    page = session_testeur.aller("/")
    assert page.locator("h1").first.inner_text().strip() == "Que souhaitez-vous faire ?"
    texte = session_testeur.texte()
    for bloc in ("Découvrir", "Explorer le catalogue", "Gérer mes collections", "Créer une nouvelle collection"):
        assert bloc in texte, f"la tuile « {bloc} » manque à l'accueil"
    assert "Il vous manque une donnée pour travailler" not in texte, "le cadre a quitté l'accueil (l'entrée Entraide du menu y mène)"
    captures.prendre(page, "02-accueil")


def test_l_exemple_de_l_accueil_ouvre_le_bac_a_sable_prerempli(session_testeur, collection_publiee, captures):
    """« Essayer cette question » mène au bac à sable de la collection, la question déjà écrite."""
    page = session_testeur.aller("/")
    bouton = page.locator("[data-tuile=decouvrir]").get_by_role("link", name=re.compile("Essayer cette question"))
    assert bouton.count() == 1, "l'accueil n'offre pas « Essayer cette question »"
    bouton.click()
    page.wait_for_url(re.compile(r"/c/[^/]+/playground"), timeout=30_000)
    page.locator("#question").wait_for(state="visible", timeout=30_000)
    assert page.locator("#question").input_value().strip(), "la question n'est pas préremplie"
    captures.prendre(page, "02-accueil-vers-bac-a-sable")


def test_le_catalogue_liste_les_collections(session_testeur, collection_publiee, captures):
    page = session_testeur.aller("/admin/catalog")
    assert page.locator("h1").first.inner_text().strip() == "Catalogue des collections"
    lignes = page.locator("tbody tr")
    lignes.first.wait_for(state="visible", timeout=30_000)
    assert lignes.count() >= 1
    liens = page.locator("tbody tr a.fr-link[href^='/c/']")
    assert liens.count() >= 1, "aucune collection cliquable dans le catalogue"
    assert page.locator(f"a[href='/c/{collection_publiee['name']}']").count() >= 1, "la collection publiée de l'accueil n'est pas dans le catalogue"
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


COLONNES = ["Collection", "État", "Créée le", "Mise à jour", "Avis des usagers", "Responsable"]


def test_les_colonnes_du_catalogue_sont_celles_de_la_maquette(session_testeur, collection_publiee):
    page = session_testeur.aller("/admin/catalog")
    page.locator("thead th").first.wait_for(state="visible", timeout=30_000)
    assert [t.strip() for t in page.locator("thead th").all_inner_texts()] == COLONNES
    assert re.search(r"\d+ collections? · \d+ catégories?", session_testeur.texte())
    assert "Une collection manque ? Contactez d'abord son responsable" in session_testeur.texte()


def _taux_par_groupe(page) -> list[list[int | None]]:
    groupes = []
    for i in range(page.locator("tbody").count()):
        lignes = page.locator("tbody").nth(i).locator("tr:has(td)")
        taux = []
        for j in range(lignes.count()):
            cellule = lignes.nth(j).locator("td").nth(4).inner_text()
            m = re.search(r"(\d+) %", cellule)
            taux.append(int(m.group(1)) if m else None)
        groupes.append(taux)
    return groupes


def test_le_tri_par_satisfaction_reordonne_chaque_categorie(session_testeur, collection_publiee):
    page = session_testeur.aller("/admin/catalog")
    page.locator("tbody tr").first.wait_for(state="visible", timeout=30_000)
    page.get_by_role("button", name="Tout déplier").click()
    page.select_option("#tri", "satisfaction")
    page.wait_for_timeout(500)
    for taux in _taux_par_groupe(page):
        notes = [t for t in taux if t is not None]
        assert notes == sorted(notes, reverse=True), taux
        assert taux == notes + [None] * (len(taux) - len(notes)), f"les collections sans avis passent en dernier : {taux}"


def test_le_catalogue_n_offre_ni_archiver_ni_purger(session_testeur):
    """Archiver et Purger vivent dans les Réglages d'une collection (refonte du 2026-10-19)."""
    page = session_testeur.aller("/admin/catalog")
    page.locator("tbody tr").first.wait_for(state="visible", timeout=30_000)
    assert page.get_by_role("button", name=re.compile(r"^(Archiver|Purger|Désarchiver)$")).count() == 0
    assert page.get_by_role("link", name=re.compile("Créer une nouvelle collection", re.I)).count() == 0


def test_la_fiche_d_une_collection_se_lit(session_testeur, collection_publiee, captures):
    page = session_testeur.aller(f"/c/{collection_publiee['name']}")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    titre = page.locator("h1").first.inner_text().strip()
    assert titre and "sans configuration" not in titre
    onglets = page.get_by_role("tab")
    libelles = [re.sub(r"\s*\(\d+\)$", "", onglets.nth(i).inner_text().strip()) for i in range(onglets.count())]
    assert libelles[:4] == ["Documents", "Signalements", "Propositions", "Historique"], libelles
    assert page.locator("[role=tab][aria-selected=true]").inner_text().startswith("Documents"), "Documents est l'onglet par défaut"
    texte = session_testeur.texte()
    assert "Ce qu'en pensent vos collègues" in texte and "Consignes données à l'assistant" in texte
    captures.prendre(page, "03-fiche-collection")

    page.get_by_role("tab", name=re.compile("Documents")).click()
    page.wait_for_timeout(1_500)
    panneau = page.get_by_role("tabpanel")
    assert panneau.count() >= 1 and panneau.first.is_visible()
    captures.prendre(page, "03-fiche-documents", mobile=False)


def test_une_adresse_inconnue_est_dite_en_francais(session_testeur, captures):
    page = session_testeur.aller("/cette-page-n-existe-pas")
    page.wait_for_timeout(1_500)
    texte = session_testeur.texte()
    captures.prendre(page, "02-page-inconnue", mobile=False)
    assert re.search(r"introuvable|n'existe pas|page inconnue", texte, re.I), texte[:200]
