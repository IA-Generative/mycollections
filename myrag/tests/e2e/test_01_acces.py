"""Avant toute chose : le service est là, l'API est fermée sans jeton, un compte hors du groupe
est refusé, et un lien partagé mène à la page qu'il désigne.

Les routes de FERMEES_P0 répondaient sans jeton jusqu'au lot P0 du diagnostic d'octobre 2026
(avis des utilisateurs, relais OpenRAG, état du service). Les vues du graphe et des articles
restent ouvertes pour une collection publiée à tous ; pour les autres, voir test_04.
"""
from __future__ import annotations

import httpx
import pytest

#: Ce qu'une API de collections doit refuser sans jeton : des lectures de données déposées.
FERMEES = [
    "/api/collections", "/api/categories", "/api/guide", "/api/demandes",
    "/api/accueil/exemple", "/api/accueil/mes-collections", "/api/ingest/jobs",
    "/api/sync/groups", "/api/qr-cache/x", "/api/eval/x/datasets", "/api/playground/x/bank",
    "/api/collections/templates", "/api/sources/check-url", "/api/bus/demandes",
]

#: Routes fermées par le lot P0 du diagnostic d'octobre 2026 (elles répondaient sans jeton).
FERMEES_P0 = [
    "/api/feedback/{collection}",            # questions et réponses des utilisateurs
    "/api/feedback/{collection}/stats",
    "/api/openrag/extract/1",                # relais OpenRAG au jeton admin : lien signé ou jeton
    "/api/openrag/static/1",
    "/api/openrag/file/1",
    "/graph/config",
    "/api/owui/probe",
]

#: La description de l'API n'est plus servie (404) — ni publique, ni derrière jeton.
DESCRIPTION_API = ["/docs", "/openapi.json", "/redoc"]


def _anonyme(cible, chemin: str) -> int:
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        return client.get(cible["base"] + chemin).status_code


def test_le_service_se_declare_sain(cible):
    with httpx.Client(timeout=20.0) as client:
        sante = client.get(cible["base"] + "/health")
        assert sante.status_code == 200 and sante.json().get("status") == "ok", sante.text
        version = client.get(cible["base"] + "/__version__")
        assert version.status_code == 200
        assert version.json()["version"] not in ("", "dev"), "l'image doit porter sa version (build-args VERSION…)"
        assert sante.json()["version"] == version.json()["version"]
        config = client.get(cible["base"] + "/api/config")
        assert config.status_code == 200 and config.json().get("app_title")


@pytest.mark.parametrize("chemin", FERMEES)
def test_l_api_est_fermee_sans_jeton(cible, chemin):
    assert _anonyme(cible, chemin) == 401


@pytest.mark.parametrize("chemin", FERMEES_P0)
def test_les_routes_de_contenu_exigent_un_jeton(cible, collection_publiee, chemin):
    """Une collection publiée à tous ne fait pas exception pour ses avis ni pour l'état du service."""
    assert _anonyme(cible, chemin.format(collection=collection_publiee["name"])) == 401


@pytest.mark.parametrize("chemin", DESCRIPTION_API)
def test_la_description_de_l_api_n_est_pas_publique(cible, chemin):
    """Le backend ne la sert plus ; l'adresse retombe sur l'application (200, sa page HTML) ou 404."""
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        r = client.get(cible["base"] + chemin)
    assert r.status_code in (200, 401, 404)
    assert not any(m in r.text.lower() for m in ("swagger", "redoc", '"openapi"')), "la description de l'API est servie"


def test_un_compte_hors_du_groupe_est_refuse(verdict_hors_groupe):
    issue, detail = verdict_hors_groupe
    assert issue == "refuse", f"le compte hors groupe n'est pas refusé : {issue} : {detail}"


def test_un_lien_partage_mene_a_la_page_demandee(navigateur, cible):
    """Un collègue reçoit le lien du guide, se connecte, et doit arriver SUR le guide."""
    from tests.e2e.conftest import _ouvrir
    issue, _, contexte = _ouvrir(navigateur, cible, "E2E_TESTEUR", obligatoire=True, chemin="/guide")
    try:
        assert issue == "entre"
        assert contexte.pages[0].url.rstrip("/").endswith("/guide")
    finally:
        contexte.close()
