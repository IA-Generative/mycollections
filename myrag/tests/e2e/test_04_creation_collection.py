"""Créer une collection par l'interface, en cinq étapes, puis la retrouver sur sa fiche.

La séquence partage la page du testeur : chaque étape reprend là où la précédente s'arrête.
"""
from __future__ import annotations

import re

import httpx
import pytest

from tests.e2e.conftest import DOCUMENT_TEMOIN, QUESTION_TEMOIN, TEMOIN, attendre


def _suivant(page):
    page.get_by_text(re.compile(r"^\s*Suivant\s*→\s*$")).last.click()


def test_etape_1_choisir_la_source(session_testeur, collection_essai, captures):
    page = session_testeur.aller("/admin/create")
    assert re.search(r"Cr[ée]er une collection", page.locator("h1").first.inner_text())
    captures.prendre(page, "05-creation-1-source")
    page.locator(".fr-card", has_text="Fichier unique").first.click()
    _suivant(page)
    page.wait_for_url(re.compile(r"/admin/create/step-2"), timeout=30_000)


def test_etape_2_identifier(session_testeur, collection_essai, captures):
    page = session_testeur.page
    assert "/admin/create/step-2" in page.url
    page.locator("#titre").fill("Note de contrôle de la suite e2e")
    page.locator("#name").fill(collection_essai)
    page.get_by_role("button", name=re.compile(r"^\s*V[ée]rifier\s*$")).click()
    verdict = page.locator(".fr-valid-text, .fr-error-text").first
    verdict.wait_for(state="visible", timeout=20_000)
    assert "disponible" in verdict.inner_text(), verdict.inner_text()
    captures.prendre(page, "05-creation-2-identification")
    _suivant(page)
    page.wait_for_url(re.compile(r"/admin/create/step-3"), timeout=60_000)
    assert session_testeur.get(f"/api/collections/{collection_essai}").status == 200, \
        "la collection créée n'est pas relue par son créateur"


def test_etape_3_deposer_le_document(session_testeur, collection_essai, captures):
    page = session_testeur.page
    page.locator("input[type=file]").set_input_files(str(DOCUMENT_TEMOIN))
    captures.prendre(page, "05-creation-3-donnees", mobile=False)
    page.get_by_role("button", name=re.compile("Charger la donn")).click()
    page.get_by_text(re.compile(r"^\s*Suivant\s*→\s*$")).last.wait_for(state="visible", timeout=180_000)

    def indexation_terminee():
        reponse = session_testeur.get(f"/api/ingest/jobs?collection={collection_essai}")
        travaux = (reponse.json() or {}).get("jobs", []) if reponse.status == 200 else []
        return next((t for t in travaux if str(t.get("status", "")).startswith("done")), None)

    travail = attendre(indexation_terminee, delai=180, motif="indexation terminée")
    assert not travail.get("failed_chunks"), f"morceaux refusés : {travail}"
    captures.prendre(page, "05-creation-3-indexee", mobile=False)
    _suivant(page)
    page.wait_for_url(re.compile(r"/admin/create/step-4"), timeout=30_000)


def test_etape_4_tester_la_collection(session_testeur, captures):
    page = session_testeur.page
    page.locator("textarea").first.fill(QUESTION_TEMOIN)
    captures.prendre(page, "05-creation-4-evaluation", mobile=False)
    page.get_by_role("button", name=re.compile(r"^\s*Tester\s*$")).click()
    attendre(lambda: TEMOIN in session_testeur.texte(), delai=180,
             motif=f"le témoin « {TEMOIN} » dans la réponse de l'étape 4")
    captures.prendre(page, "05-creation-4-reponse", mobile=False)
    _suivant(page)
    page.wait_for_url(re.compile(r"/admin/create/step-5"), timeout=30_000)


def test_etape_5_dit_ce_qui_suit_et_mene_a_la_fiche(session_testeur, collection_essai, captures):
    page = session_testeur.page
    texte = session_testeur.texte()
    captures.prendre(page, "05-creation-5-partage")
    assert "en cours de vérification" in texte, "l'étape 5 doit dire que la collection est à vérifier avant d'être ouverte à tous"
    for promesse in ("embed.js", "Extension navigateur", "Tool MyRAG", "localhost"):
        assert promesse not in texte, f"l'étape 5 promet encore « {promesse} »"
    page.get_by_role("button", name="Terminer").click()
    page.get_by_role("link", name=re.compile("Ouvrir la fiche de la collection")).click()
    page.wait_for_url(re.compile(rf"/c/{collection_essai}"), timeout=30_000)
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    assert "Note de contrôle" in page.locator("h1").first.inner_text()
    captures.prendre(page, "05-creation-6-fiche-creee")


def test_un_pdf_est_refuse_avec_une_explication(session_testeur, collection_essai):
    """Le découpage lit du texte : un PDF partait indexé illisible, sans un mot."""
    r = session_testeur.page.request.post(
        f"{session_testeur.base}/api/ingest/{collection_essai}",
        headers={"Authorization": f"Bearer {session_testeur.jeton}"},
        multipart={"file": {"name": "a.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.7 binaire"}})
    assert r.status == 415 and "texte" in r.text()


def test_un_lien_de_graphe_d_une_collection_non_publique_est_ferme_sans_signature(cible, collection_essai, session_testeur):
    """Les vues ouvertes sans jeton (graphe, articles) ne servent une collection non publiée à
    tous que par un lien signé ; la fiche en obtient un pour son iframe."""
    import httpx
    with httpx.Client(timeout=20.0) as client:
        assert client.get(f"{cible['base']}/graph/data?corpus_id={collection_essai}").status_code == 401
        assert client.get(f"{cible['base']}/articles/{collection_essai}/1").status_code == 401
        lien = session_testeur.get(f"/graph/{collection_essai}/lien").json()["url"]
        assert client.get(cible["base"] + lien.replace("/graph?", "/graph/data?")).status_code == 200
