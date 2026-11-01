"""GET /api/v1/search?assistant=<id> : sans le paramètre, la réponse est celle de toujours ;
avec, elle vient du plan de l'assistant (le planificateur par règles, comme `plan`/`executer` et
le serveur MCP, sans réponse fiable) et porte une clé `plan`."""

from __future__ import annotations

import pytest

from app.config import settings
from tests.conftest import SUPERADMIN
from tests.harnais.conftest import IDENTITES, fiche_d_essai
from tests.harnais.test_fiables import QUESTION, _semer, _servie
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


#: Ressemble à la fiche de `partagee` (« Méthodes de l'équipe ») : la source `selon_question` est retenue.
SUR_LES_METHODES = "Les méthodes de l'équipe pour le budget"


def test_avec_assistant_les_resultats_viennent_du_plan(client, en_tant_que, jeu, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": SUR_LES_METHODES, "assistant": assistant_publie})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert set(corps) == {"source", "query", "total", "truncated", "total_is_lower_bound", "results", "plan"}
    assert corps["source"] == "mycollections" and corps["query"] == SUR_LES_METHODES
    plan = corps["plan"]
    assert plan["assistant"] == assistant_publie and plan["planificateur"] == "regles" and plan["version"] == 1
    assert plan["consigne"] is None and plan["reponse_fiable"] is None
    # `mienne` (toujours), `partagee` (selon_question, elle ressemble à la question), par rang.
    assert [e["source"] for e in plan["etapes"]] == [jeu["mienne"], jeu["partagee"]]
    assert plan["sources_ignorees"] == 0  # `secrete` (sur_consigne) n'était pas visée : rien d'écarté
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
    corps = client.get("/api/v1/search", params={"q": SUR_LES_METHODES, "assistant": assistant_publie, "limit": "1"}).json()
    assert len(corps["results"]) == 1 and corps["truncated"] is True and corps["total"] == 2


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


# ─── Le plan suit la fiche : régimes, consignes, pas de réponse fiable ─────────────────────


def test_une_source_sur_consigne_n_est_pas_interrogee_sans_consigne_qui_la_cite(client, en_tant_que, jeu, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["bob"])  # lit `partagee` et `secrete` (sur_consigne), pas `mienne`
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert [e["source"] for e in corps["plan"]["etapes"]] == [jeu["partagee"]]
    assert theatre_branche.sources_appelees() == [jeu["partagee"]]
    assert {x["context"]["collection"]["id"] for x in corps["results"]} == {jeu["partagee"]}


@pytest.fixture
def assistant_a_consignes(client, en_tant_que, jeu, ident_assistant):
    """Publié par l'administration, avec une consigne qui cite `secrete` en deuxième étape, relayée."""
    en_tant_que(SUPERADMIN)
    consigne = {
        "id": "methodes",
        "quand": "Une question sur les méthodes de budget de l'équipe",
        "exemples": ["Comment est voté le budget ?"],
        "chercher": [{"source": jeu["partagee"]}, {"source": jeu["secrete"], "avec": "article_trouve"}],
    }
    fiche = fiche_d_essai(jeu, ident_assistant, consignes=[consigne])
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche.model_dump(mode="json")).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    return ident_assistant


@pytest.mark.parametrize("qui", ["alice", "bob"])
def test_une_question_qui_ressemble_a_une_consigne_suit_ses_etapes(client, en_tant_que, jeu, assistant_a_consignes, theatre_branche, qui):
    question = "Comment est voté le budget ?"
    en_tant_que(IDENTITES[qui])
    attendu = client.post(f"/api/v1/assistants/{assistant_a_consignes}/plan", json={"question": question})
    assert attendu.status_code == 200, attendu.text
    r = client.get("/api/v1/search", params={"q": question, "assistant": assistant_a_consignes})
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert plan == attendu.json()  # le même plan que le bac à sable, pour la même personne
    assert plan["consigne"] == "methodes" and plan["etapes"][0]["source"] == jeu["partagee"]
    if qui == "bob":  # lit `secrete` : l'étape « avec » a reçu le meilleur passage de la première
        amont = next(a for _, s, a in theatre_branche.appels if s == jeu["secrete"])
        assert [p.source for p in amont] == [jeu["partagee"]]
        assert {x["context"]["collection"]["id"] for x in r.json()["results"]} == {jeu["partagee"], jeu["secrete"]}
    else:  # Alice ne lit pas `secrete` : écartée, comptée, jamais nommée ; `mienne` (toujours) s'ajoute
        assert [e["source"] for e in plan["etapes"]] == [jeu["partagee"], jeu["mienne"]]
        assert plan["sources_ignorees"] == 1 and jeu["secrete"] not in r.text


def test_une_reponse_fiable_n_est_pas_servie_par_la_recherche_v1(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    """Le contrat v1 n'a pas de champ réponse : la recherche cherche, sans servir ni compter la réponse fiable."""
    q = _semer(client, en_tant_que, jeu["partagee"])
    en_tant_que(SUPERADMIN)
    fiche = fiche_d_essai(jeu, ident_assistant)
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche.model_dump(mode="json")).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    en_tant_que(IDENTITES["alice"])
    assert client.post(f"/api/v1/assistants/{ident_assistant}/plan", json={"question": QUESTION}).json()["reponse_fiable"]["id"] == q
    r = client.get("/api/v1/search", params={"q": QUESTION, "assistant": ident_assistant})
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert plan["planificateur"] == "regles" and plan["reponse_fiable"] is None and plan["etapes"]
    assert theatre_branche.appels and r.json()["results"]
    assert _servie(q)[0] == 0
