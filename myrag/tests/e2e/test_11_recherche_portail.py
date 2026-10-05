"""La recherche de Mon portail (contrat de recherche MirAI) sur la cible déployée.

Mon portail appelle `/api/v1/search` depuis le navigateur avec le jeton de la personne. Ici, le
jeton est celui de la session du testeur (le front de Mes collections, accepté par son `azp`) :
le parcours prouve les droits, le périmètre et les erreurs, pas la configuration du client
`mysearch` du SSO. Aucun appel à un modèle de langage derrière ces routes.
"""
from __future__ import annotations

import re

import httpx

DROITS = {"owner", "reader", "public"}
GROUPES = {"mine", "shared", "public"}


def _perimetres(session) -> dict[str, dict]:
    r = session.get("/api/v1/search/scopes")
    assert r.status == 200, r.text()
    assert r.headers.get("cache-control") == "no-store"
    scopes = r.json()["scopes"]
    for s in scopes:
        assert s["right"] in DROITS and s["group"] in GROUPES, s
        assert "file_count" not in s
    return {s["id"]: s for s in scopes}


def _chercher(session, **params):
    return session.get("/api/v1/search", params=params)


def test_les_perimetres_sont_les_collections_lisibles(session_testeur, collection_publiee):
    lisibles = _perimetres(session_testeur)
    assert collection_publiee["name"] in lisibles
    assert lisibles[collection_publiee["name"]]["right"] in ("public", "owner", "reader")


def test_la_recherche_ne_rend_que_des_collections_lisibles(session_testeur, collection_publiee):
    lisibles = _perimetres(session_testeur)
    q = (collection_publiee.get("question") or collection_publiee.get("titre") or collection_publiee["name"])[:200]
    r = _chercher(session_testeur, q=q, limit="10")
    assert r.status == 200, r.text()
    assert r.headers.get("cache-control") == "no-store"
    corps = r.json()
    assert corps["source"] == "mycollections" and corps["query"] == q.strip()
    assert corps["truncated"] == (corps["total"] > len(corps["results"]))
    for res in corps["results"]:
        assert res["context"]["collection"]["id"] in lisibles
        assert res["context"]["right"] in DROITS
        assert res["url"] is None or res["url"].startswith("https://")
        assert 1 <= len(res["hits"]) <= 3
        for hit in res["hits"]:
            assert not re.search(r"<[a-zA-Z/!][^>]*>", hit["snippet"]), "un extrait contient du HTML"
            assert len(hit["snippet"]) <= 320


def test_un_perimetre_inconnu_est_ignore(session_testeur, collection_publiee):
    inconnu = "e2e-inconnue-zz9"
    r = _chercher(session_testeur, q="contrôle", scope=inconnu)
    assert r.status == 200, r.text()
    assert r.json()["total"] == 0 and r.json()["results"] == []

    r = _chercher(session_testeur, q=collection_publiee.get("question") or "contrôle",
                  scope=f"{inconnu},{collection_publiee['name']}")
    assert r.status == 200, r.text()
    assert {x["context"]["collection"]["id"] for x in r.json()["results"]} <= {collection_publiee["name"]}


def test_une_requete_invalide_est_dite(session_testeur):
    r = _chercher(session_testeur, q="", limit="10")
    assert r.status == 400 and r.json()["error"]["code"] == "invalid_query"


def test_sans_jeton_401(cible):
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        for chemin in ("/api/v1/search?q=contr%C3%B4le", "/api/v1/search/scopes"):
            r = client.get(cible["base"] + chemin)
            assert r.status_code == 401, chemin
            assert r.json()["error"]["code"] == "invalid_token"
            assert r.headers.get("cache-control") == "no-store"
