"""GET /api/v1/search?assistant=<id> : sans le paramètre, la réponse est celle de toujours ;
avec, elle vient du plan de l'assistant et porte une clé `plan`."""

from __future__ import annotations

import pytest

from app.config import settings
from tests.harnais.conftest import IDENTITES
from tests.non_regression._outils import figer
from tests.non_regression.test_recherche_v1 import _documents, _normaliser, _rendu
from tests.unit.test_recherche import ALICE, PORTAIL, jeu, moteur, noms, reglages  # noqa: F401 — jeu et simulateur de la recherche v1


def test_sans_assistant_le_corps_est_celui_des_fixtures(client, en_tant_que, jeu, moteur):  # noqa: F811
    en_tant_que(ALICE)
    moteur.return_value = _rendu(_documents(jeu))
    r = client.get("/api/v1/search", params={"q": "budget"})
    assert r.status_code == 200, r.text
    assert "plan" not in r.json()
    figer("recherche_v1/search_sans_scope", _normaliser(r.json(), jeu))
    r = client.get("/api/v1/search", params={"q": "budget", "scope": f"{jeu['partagee']},{jeu['secrete']}", "limit": "1"})
    figer("recherche_v1/search_avec_scope", _normaliser(r.json(), jeu))


def test_avec_assistant_les_resultats_viennent_du_plan(client, en_tant_que, jeu, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert set(corps) == {"source", "query", "total", "truncated", "total_is_lower_bound", "results", "plan"}
    assert corps["source"] == "mycollections" and corps["query"] == "budget"
    plan = corps["plan"]
    assert plan["assistant"] == assistant_publie and plan["planificateur"] == "toutes_les_sources" and plan["version"] == 1
    assert [e["source"] for e in plan["etapes"]] == [jeu["mienne"], jeu["partagee"]]  # par rang, `secrete` en moins
    assert plan["sources_ignorees"] == 1
    # La forme des résultats est celle du contrat v1, liens signés compris.
    premier = corps["results"][0]
    assert set(premier) == {"id", "title", "date", "url", "score", "hits", "context"}
    assert premier["context"]["collection"]["id"] in {jeu["mienne"], jeu["partagee"]}
    assert premier["url"].startswith("https://mycollections.fake-domain.name/api/openrag/extract/") and "sig=" in premier["url"]
    assert set(premier["hits"][0]) == {"snippet", "highlights", "field", "location", "speaker", "url"}
    droits = {x["context"]["collection"]["id"]: x["context"]["right"] for x in corps["results"]}
    assert droits == {jeu["mienne"]: "owner", jeu["partagee"]: "reader"}


def test_la_limite_borne_les_resultats(client, en_tant_que, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    corps = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie, "limit": "1"}).json()
    assert len(corps["results"]) == 1 and corps["truncated"] is True


@pytest.mark.parametrize("ident", ["assistant-inconnu", "x"])
def test_assistant_inconnu_404(client, en_tant_que, theatre_branche, ident):
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": ident})
    assert r.status_code == 404 and r.json() == {"error": {"code": "not_found", "message": "Introuvable"}}
    assert theatre_branche.appels == []


def test_assistant_hors_droit_404(client, en_tant_que, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["dehors"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_assistant_jamais_publie_404(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    from tests.conftest import SUPERADMIN
    from tests.harnais.conftest import fiche_d_essai

    en_tant_que(SUPERADMIN)
    client.put(f"/api/assistants/{ident_assistant}", json=fiche_d_essai(jeu, ident_assistant).model_dump(mode="json"))
    assert client.get("/api/v1/search", params={"q": "budget", "assistant": ident_assistant}).status_code == 404


def test_drapeau_assistants_faux_404(client, en_tant_que, assistant_publie, theatre_branche, capacites):
    en_tant_que(IDENTITES["alice"])
    capacites(assistants=False)
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert theatre_branche.appels == []


def test_toutes_les_sources_en_panne_503(client, en_tant_que, jeu, assistant_publie, theatre_de, monkeypatch):
    import httpx

    panne = httpx.ConnectError("coupé")
    theatre = theatre_de(pannes={jeu["mienne"]: panne, jeu["partagee"]: panne})
    monkeypatch.setattr("app.services.assistant_recherche.ConnecteurOpenRAG", lambda **_: theatre)
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 503 and r.json()["error"]["code"] == "search_unavailable"


def test_cors_et_audience_inchanges(client, en_tant_que, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie}, headers={"Origin": PORTAIL})
    assert r.headers["access-control-allow-origin"] == PORTAIL and "access-control-allow-credentials" not in r.headers
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie}, headers={"Origin": "https://autre.fake-domain.name"})
    assert "access-control-allow-origin" not in r.headers
    assert settings.recherche_audience  # la garde de jeton est celle de la route : même dépendance, pas de variante
