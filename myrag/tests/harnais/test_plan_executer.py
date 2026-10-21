"""POST /api/v1/assistants/{id}/plan et /executer : les routes réelles, leurs droits, la
re-validation d'un plan rendu par le client, et la cohabitation avec la doublure."""

from __future__ import annotations

import os
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.harnais.contrat import Plan, Resultat
from app.routers import assistants_doublure
from tests.conftest import SUPERADMIN
from tests.harnais.conftest import IDENTITES, fiche_d_essai


def _url(ident: str, suite: str) -> str:
    return f"/api/v1/assistants/{ident}/{suite}"


@pytest.fixture
def assistant_a_consignes(client, en_tant_que, jeu, ident_assistant):
    """Publié par l'administration, avec une consigne qui cite `secrete` en deuxième étape."""
    en_tant_que(SUPERADMIN)
    fiche = fiche_d_essai(
        jeu,
        ident_assistant,
        consignes=[
            {
                "id": "methodes",
                "quand": "Une question sur les méthodes de budget de l'équipe",
                "exemples": ["Comment est voté le budget ?"],
                "chercher": [{"source": jeu["partagee"]}, {"source": jeu["secrete"], "avec": "article_trouve"}],
            }
        ],
    )
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche.model_dump(mode="json")).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    return ident_assistant


def test_plan_reel_une_consigne_reconnue_et_le_perimetre_de_la_personne(client, en_tant_que, jeu, assistant_a_consignes):
    en_tant_que(IDENTITES["alice"])
    r = client.post(_url(assistant_a_consignes, "plan"), json={"question": "Comment est voté le budget ?"})
    assert r.status_code == 200, r.text
    assert "x-mycollections-doublure" not in r.headers
    plan = Plan.model_validate(r.json())
    assert plan.planificateur == "regles" and plan.consigne == "methodes" and plan.assistant == assistant_a_consignes
    # Alice ne lit pas `secrete` : l'étape est écartée, comptée, jamais nommée ; `mienne` (toujours) s'ajoute.
    assert [e.source for e in plan.etapes] == [jeu["partagee"], jeu["mienne"]]
    assert plan.sources_ignorees == 1 and jeu["secrete"] not in r.text
    # Bob, lui, lit `secrete` : l'étape « avec » attend la première.
    en_tant_que(IDENTITES["bob"])
    plan_bob = Plan.model_validate(client.post(_url(assistant_a_consignes, "plan"), json={"question": "Comment est voté le budget ?"}).json())
    assert [(e.source, e.attend, e.avec) for e in plan_bob.etapes[:2]] == [(jeu["partagee"], [], None), (jeu["secrete"], [1], "article_trouve")]


def test_executer_sans_plan_planifie_puis_cherche(client, en_tant_que, jeu, assistant_a_consignes, theatre_branche):
    en_tant_que(IDENTITES["bob"])
    r = client.post(_url(assistant_a_consignes, "executer"), json={"question": "Comment est voté le budget ?"})
    assert r.status_code == 200, r.text
    resultat = Resultat.model_validate(r.json())
    assert resultat.plan.consigne == "methodes"
    assert set(resultat.par_source) == {jeu["partagee"], jeu["secrete"]}
    assert {p.source for p in resultat.passages} == {jeu["partagee"], jeu["secrete"]}  # Bob ne lit pas `mienne`
    assert resultat.duree_ms >= 0 and resultat.reponse is None
    # L'étape « avec » a reçu le meilleur passage de la première.
    amont = next(a for n, s, a in theatre_branche.appels if s == jeu["secrete"])
    assert [p.source for p in amont] == [jeu["partagee"]]


def test_un_plan_modifie_avec_une_source_hors_fiche_est_refuse(client, en_tant_que, jeu, assistant_a_consignes, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    plan = Plan(assistant=assistant_a_consignes, version=1, planificateur="regles", etapes=[{"n": 1, "source": jeu["ouverte"], "question": "budget"}]).model_dump(mode="json")
    r = client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget", "plan": plan})
    assert r.status_code == 400
    assert theatre_branche.appels == []
    autre = {**plan, "assistant": "un-autre-assistant", "etapes": [{"n": 1, "source": jeu["partagee"], "question": "budget", "poids": 1.0, "attend": []}]}
    assert client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget", "plan": autre}).status_code == 400


def test_un_plan_modifie_avec_une_source_hors_droit_est_ignoree(client, en_tant_que, jeu, assistant_a_consignes, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    etapes = [{"n": 1, "source": jeu["partagee"], "question": "budget"}, {"n": 2, "source": jeu["secrete"], "question": "budget", "attend": [1], "avec": "relais"}]
    plan = Plan(assistant=assistant_a_consignes, version=1, planificateur="regles", etapes=etapes).model_dump(mode="json")
    r = client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget", "plan": plan})
    assert r.status_code == 200, r.text
    resultat = Resultat.model_validate(r.json())
    assert [e.source for e in resultat.plan.etapes] == [jeu["partagee"]] and resultat.plan.sources_ignorees == 1
    assert jeu["secrete"] not in r.text and theatre_branche.sources_appelees() == [jeu["partagee"]]


def test_brouillon_pour_qui_modifie_version_publiee_pour_les_autres(client, en_tant_que, jeu, assistant_a_consignes, theatre_branche):
    # Le brouillon n'a plus que `mienne` ; la version publiée en a trois.
    en_tant_que(SUPERADMIN)
    brouillon = fiche_d_essai(jeu, assistant_a_consignes)
    brouillon = brouillon.model_copy(update={"sources": [s for s in brouillon.sources if s.id == jeu["mienne"]], "consignes": []})
    assert client.put(f"/api/assistants/{assistant_a_consignes}", json=brouillon.model_dump(mode="json")).status_code == 200
    q = {"question": "Comment est voté le budget ?"}
    vu_par_admin = Resultat.model_validate(client.post(_url(assistant_a_consignes, "executer"), json=q).json())
    assert [e.source for e in vu_par_admin.plan.etapes] == [jeu["mienne"]] and vu_par_admin.plan.consigne is None
    en_tant_que(IDENTITES["alice"])  # gère `mienne`, la seule source du brouillon : elle le modifie, elle le sert
    vu_par_alice = Resultat.model_validate(client.post(_url(assistant_a_consignes, "executer"), json=q).json())
    assert [e.source for e in vu_par_alice.plan.etapes] == [jeu["mienne"]]
    en_tant_que(IDENTITES["bob"])  # ne lit pas le brouillon, lit la version publiée : celle-ci
    vu_par_bob = Resultat.model_validate(client.post(_url(assistant_a_consignes, "executer"), json=q).json())
    assert vu_par_bob.plan.consigne == "methodes" and jeu["partagee"] in {e.source for e in vu_par_bob.plan.etapes}
    assert jeu["mienne"] not in {p.source for p in vu_par_bob.passages}


def test_assistant_jamais_publie_visible_seulement_de_qui_le_modifie(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    en_tant_que(SUPERADMIN)
    client.put(f"/api/assistants/{ident_assistant}", json=fiche_d_essai(jeu, ident_assistant).model_dump(mode="json"))
    assert client.post(_url(ident_assistant, "executer"), json={"question": "budget"}).status_code == 200
    en_tant_que(IDENTITES["alice"])
    assert client.post(_url(ident_assistant, "executer"), json={"question": "budget"}).status_code == 404
    assert client.post(_url(ident_assistant, "plan"), json={"question": "budget"}).status_code == 404


def test_inconnu_hors_droit_et_drapeau_faux(client, en_tant_que, assistant_a_consignes, theatre_branche, capacites):
    en_tant_que(IDENTITES["alice"])
    assert client.post(_url("inconnu-assistant", "executer"), json={"question": "q"}).status_code == 404
    en_tant_que(IDENTITES["dehors"])
    assert client.post(_url(assistant_a_consignes, "plan"), json={"question": "q"}).status_code == 404
    en_tant_que(IDENTITES["alice"])
    capacites(assistants=False)
    assert client.post(_url(assistant_a_consignes, "executer"), json={"question": "q"}).status_code == 404
    assert theatre_branche.appels == []


def test_le_canal_bac_a_sable_est_journalise(client, en_tant_que, assistant_a_consignes, theatre_branche):
    en_tant_que(IDENTITES["bob"])
    client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget", "canal": "bac-a-sable"})
    client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget"})
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        canaux = [c for (c,) in con.execute("SELECT canal FROM plans_journal WHERE assistant_id = ? ORDER BY cree_le", (assistant_a_consignes,))]
        planificateurs = {p for (p,) in con.execute("SELECT planificateur FROM plans_journal WHERE assistant_id = ?", (assistant_a_consignes,))}
    finally:
        con.close()
    assert canaux == ["bac-a-sable", "api"] and planificateurs == {"regles"}
    assert client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget", "canal": "portail"}).status_code == 422


def test_toutes_les_sources_en_panne_503_en_francais(client, en_tant_que, jeu, assistant_a_consignes, theatre_de, monkeypatch):
    import httpx

    theatre = theatre_de(pannes={n: httpx.ConnectError("coupé") for n in jeu.values()})
    monkeypatch.setattr("app.services.assistant_recherche.ConnecteurOpenRAG", lambda **_: theatre)
    en_tant_que(IDENTITES["bob"])
    r = client.post(_url(assistant_a_consignes, "executer"), json={"question": "budget"})
    assert r.status_code == 503 and "ne répond pas" in r.json()["detail"]


# ─── La doublure : elle répond encore sur demande, et le dit ─────────────────────────────────


def test_avec_la_doublure_demandee_elle_repond_avec_son_entete(client, en_tant_que, monkeypatch):
    monkeypatch.setattr(settings, "doublure_assistants", True)
    en_tant_que(IDENTITES["dehors"])  # la doublure ne regarde ni la fiche ni les droits
    p = client.post(_url("assistant-quelconque", "plan"), json={"question": "q"})
    e = client.post(_url("assistant-quelconque", "executer"), json={"question": "q"})
    assert p.status_code == e.status_code == 200
    assert p.headers["x-mycollections-doublure"] == e.headers["x-mycollections-doublure"] == "1"
    assert Plan.model_validate(p.json()).assistant == "assistant-quelconque" and Resultat.model_validate(e.json())


def test_sans_la_doublure_pas_d_entete(client, en_tant_que, assistant_a_consignes, theatre_branche):
    assert settings.doublure_assistants is False
    en_tant_que(IDENTITES["bob"])
    for suite in ("plan", "executer"):
        r = client.post(_url(assistant_a_consignes, suite), json={"question": "budget"})
        assert r.status_code == 200 and "x-mycollections-doublure" not in r.headers


def test_la_doublure_montee_seule_porte_l_entete_sur_chaque_reponse():
    appli = FastAPI()
    appli.include_router(assistants_doublure.router)
    with TestClient(appli) as c:
        for suite in ("plan", "executer"):
            r = c.post(_url("mon-assistant", suite), json={"question": "q"})
            assert r.status_code == 200 and r.headers["x-mycollections-doublure"] == "1"


def test_aucune_route_n_a_disparu():
    from app.main import app

    chemins = app.openapi()["paths"]
    for suite in ("plan", "executer"):
        assert "post" in chemins[f"/api/v1/assistants/{{ident}}/{suite}"]
    for chemin in ("/api/assistants", "/api/assistants/{ident}", "/api/assistants/{ident}/publier", "/api/assistants/{ident}/versions"):
        assert chemin in chemins
    assert {r.path for r in assistants_doublure.router.routes} == {"/api/v1/assistants/{ident}/plan", "/api/v1/assistants/{ident}/executer"}
