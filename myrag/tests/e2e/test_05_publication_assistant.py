"""De « amorcée » à « publiée à tous », puis dans Mon assistant : la preuve de l'export.

Le circuit de vérification est joué par l'interface (grille, relecture, passages d'état,
page de publication). La preuve, elle, est lue avec le compte du testeur dans l'assistant :
le modèle est dans SA liste et il répond avec le témoin. Jamais avec une clé d'administration,
qui voit des modèles cachés aux autres.
"""
from __future__ import annotations

import re

import pytest

from tests.e2e._sso import chez_le_sso
from tests.e2e.conftest import QUESTION_TEMOIN, TEMOIN, attendre

LIGNES = {
    "Source et licence": "Note rédigée par la suite de tests, sans licence à respecter.",
    "Données personnelles": "Aucune.",
    "Fraîcheur": "Rédigée le jour de la campagne.",
}


def test_la_grille_de_controle_se_complete(session_testeur, collection_essai, captures):
    page = session_testeur.aller(f"/c/{collection_essai}")
    page.get_by_role("tab", name=re.compile("Consulter")).click()
    page.get_by_role("button", name="Compléter la grille").click()
    for libelle, valeur in LIGNES.items():
        page.get_by_label(libelle).fill(valeur)
    captures.prendre(page, "06-grille-remplie", mobile=False)
    page.get_by_role("button", name="Enregistrer").click()
    page.wait_for_timeout(1_200)
    page.get_by_role("button", name="Je relis cette collection").click()
    page.wait_for_timeout(1_200)
    reponse = session_testeur.get(f"/api/collections/{collection_essai}/grille").json()
    grille = reponse.get("grille", reponse)
    assert grille.get("complete") is True, reponse


def test_la_collection_avance_jusqu_a_publiee_a_tous(session_testeur, collection_essai, captures):
    page = session_testeur.aller(f"/c/{collection_essai}")
    for attendu in ("en_controle", "publiee_groupe", "publiee_tous"):
        bouton = page.get_by_role("button", name=re.compile(r"^Passer en «")).first
        bouton.wait_for(state="visible", timeout=30_000)
        if attendu == "en_controle":
            captures.prendre(page, "06-etat-amorcee", mobile=False)
        bouton.click()
        if attendu == "publiee_tous":  # geste qui engage : il se confirme
            page.get_by_role("button", name="Confirmer").click()
        attendre(lambda: session_testeur.get(f"/api/collections/{collection_essai}/etat").json().get("etat") == attendu,
                 delai=30, pas=1, motif=f"l'état « {attendu} »")
        page.wait_for_timeout(800)
    captures.prendre(page, "06-etat-publiee-a-tous", mobile=False)


def test_publier_a_tous_par_la_page_de_publication(session_testeur, collection_essai, captures):
    page = session_testeur.aller(f"/c/{collection_essai}/publish")
    page.locator("#vis-all").wait_for(state="attached", timeout=30_000)
    assert page.locator("#vis-all").is_enabled(), "« Tout le monde » reste interdit après « publiée à tous »"
    assert page.locator("#alias").is_checked(), "la case « proposer dans l'assistant » doit être cochée par défaut"
    page.locator("label[for=vis-all]").click()
    captures.prendre(page, "06-publication-a-tous", mobile=False)
    page.get_by_role("button", name=re.compile(r"^(Publier|Partager dans Mon assistant|Mettre à jour)$")).click()
    attendre(lambda: page.locator(".fr-alert--success, .fr-alert--warning, .fr-alert--error").count() > 0,
             delai=90, pas=1, motif="le retour de la publication")
    captures.prendre(page, "06-publication-resultat", mobile=False)
    publication = session_testeur.get(f"/api/collections/{collection_essai}/publication").json()
    assert publication.get("visibility") == "all" and publication.get("state") == "published", publication


def test_le_testeur_voit_la_collection_dans_l_assistant_et_elle_repond(session_testeur, collection_essai, cible, captures):
    if not cible["assistant"]:
        pytest.skip("E2E_ASSISTANT_URL absent : la preuve dans l'assistant n'est pas jouée")
    page = session_testeur.contexte.new_page()
    try:
        page.goto(cible["assistant"] + "/", wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(4_000)
        assert not chez_le_sso(page.url, cible["sso"]), "l'assistant n'a pas ouvert la session du testeur"
        captures.prendre(page, "07-assistant", mobile=False)
        modeles = page.request.get(cible["assistant"] + "/api/models")
        assert modeles.status == 200, modeles.status
        vus = [m.get("id") for m in (modeles.json() or {}).get("data", [])]
        assert f"openrag-{collection_essai}" in vus, f"absente de la liste du testeur : {vus}"
        essai = page.request.post(
            cible["assistant"] + "/api/chat/completions",
            data={"model": f"openrag-{collection_essai}", "stream": False,
                  "messages": [{"role": "user", "content": QUESTION_TEMOIN}]},
            timeout=180_000)
        assert essai.status == 200, f"{essai.status} : {essai.text()[:200]}"
        contenu = (essai.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        assert TEMOIN in contenu, f"répond sans le témoin : {contenu[:300]}"
    finally:
        page.close()


def test_depublier_retire_la_collection_de_l_assistant(session_testeur, collection_essai, cible):
    assert session_testeur.post(f"/api/collections/{collection_essai}/unpublish", {}).status == 200
    if not cible["assistant"]:
        return
    page = session_testeur.contexte.new_page()
    try:
        page.goto(cible["assistant"] + "/", wait_until="networkidle", timeout=60_000)
        modeles = page.request.get(cible["assistant"] + "/api/models")
        vus = [m.get("id") for m in (modeles.json() or {}).get("data", [])]
        assert f"openrag-{collection_essai}" not in vus, "toujours offerte après dépublication"
    finally:
        page.close()
