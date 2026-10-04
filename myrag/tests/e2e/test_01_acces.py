"""Avant toute chose : le service est là, l'API est fermée sans jeton, un compte hors du groupe
est refusé, et un lien partagé mène à la page qu'il désigne.

Les routes « ouvertes » listées plus bas répondent AUJOURD'HUI sans jeton, alors que tout le
reste de l'API exige un jeton : chaque ligne est un constat du diagnostic d'octobre 2026,
documenté par un `xfail` strict qui cassera quand la garde sera posée.
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

#: Routes qui devraient répondre 401 et ne le font pas (constats P0/P1 du diagnostic).
OUVERTES_CONSTATEES = {
    "/api/feedback/{collection}": "P0 : les questions et réponses des utilisateurs se lisent sans jeton (routeur feedback monté sans garde, app/main.py)",
    "/api/feedback/{collection}/stats": "P0 : statistiques d'avis lisibles sans jeton",
    "/api/openrag/extract/1": "P0 : relais vers OpenRAG avec le jeton admin, sans jeton côté appelant (404 au lieu de 401 : la route cherche l'objet avant de demander qui appelle)",
    "/articles/{collection}/1": "P1 : vue article sans garde (404 au lieu de 401)",
    "/graph/data?collection={collection}": "P1 : données du graphe sans garde (400 au lieu de 401)",
    "/graph/config": "P2 : configuration du visualiseur lisible sans jeton",
    "/api/owui/probe": "P2 : diagnostic du socle lisible sans jeton",
    "/docs": "P2 : la description complète de l'API est publique (/docs, /openapi.json, /redoc)",
}


def _anonyme(cible, chemin: str) -> int:
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        return client.get(cible["base"] + chemin).status_code


def test_le_service_se_declare_sain(cible):
    with httpx.Client(timeout=20.0) as client:
        sante = client.get(cible["base"] + "/health")
        assert sante.status_code == 200 and sante.json().get("status") == "ok"
        config = client.get(cible["base"] + "/api/config")
        assert config.status_code == 200 and config.json().get("app_title")


@pytest.mark.parametrize("chemin", FERMEES)
def test_l_api_est_fermee_sans_jeton(cible, chemin):
    assert _anonyme(cible, chemin) == 401


@pytest.mark.parametrize("chemin", [
    pytest.param(c, marks=pytest.mark.xfail(strict=True, reason=motif))
    for c, motif in OUVERTES_CONSTATEES.items()
])
def test_les_routes_de_contenu_exigent_un_jeton(cible, collection_publiee, chemin):
    """Attendu : 401. Ces routes servent du contenu d'une collection ou l'état du service."""
    assert _anonyme(cible, chemin.format(collection=collection_publiee["name"])) == 401


def test_un_compte_hors_du_groupe_est_refuse(verdict_hors_groupe):
    issue, detail = verdict_hors_groupe
    assert issue == "refuse", f"le compte hors groupe n'est pas refusé : {issue} : {detail}"


@pytest.mark.xfail(strict=True, reason="P1 : après la connexion, l'application remplace l'adresse par « / » (useAuth.ts) : un lien partagé atterrit à l'accueil")
def test_un_lien_partage_mene_a_la_page_demandee(navigateur, cible):
    """Un collègue reçoit le lien du guide, se connecte, et doit arriver SUR le guide."""
    from tests.e2e.conftest import _ouvrir
    issue, _, contexte = _ouvrir(navigateur, cible, "E2E_TESTEUR", obligatoire=True, chemin="/guide")
    try:
        assert issue == "entre"
        assert contexte.pages[0].url.rstrip("/").endswith("/guide")
    finally:
        contexte.close()
