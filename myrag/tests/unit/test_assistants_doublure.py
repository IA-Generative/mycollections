"""La doublure du harnais : ses fichiers sont conformes au contrat (elle ne peut pas en
dériver), elle répond sous les adresses que servira le lot A, et elle n'est montée que si on
l'a demandé."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.harnais.contrat import FicheAssistant, FicheSource, Plan, Resultat
from app.routers import assistants_doublure as doublure

REP = doublure.REP


def _json(nom: str):
    return json.loads((REP / nom).read_text(encoding="utf-8"))


@pytest.mark.parametrize("nom, modele", [("fiche.json", FicheAssistant), ("plan.json", Plan), ("resultat.json", Resultat), ("fiches_sources.json", TypeAdapter(list[FicheSource]))])
def test_les_fichiers_sont_conformes_au_contrat(nom, modele):
    donnees = _json(nom)
    valide = modele.validate_python(donnees) if isinstance(modele, TypeAdapter) else modele.model_validate(donnees)
    assert valide


def test_le_resultat_porte_le_plan_et_des_passages_de_chaque_etape():
    r = Resultat.model_validate(_json("resultat.json"))
    assert {p.etape for p in r.passages} == {e.n for e in r.plan.etapes}
    assert r.par_source == {s: sum(1 for p in r.passages if p.source == s) for s in r.par_source}
    fiche = FicheAssistant.model_validate(_json("fiche.json"))
    assert {e.source for e in r.plan.etapes} <= {s.id for s in fiche.sources}


@pytest.fixture
def appli():
    a = FastAPI()
    a.include_router(doublure.router)
    with TestClient(a) as c:
        yield c


def test_plan_et_execution(appli):
    p = appli.post("/api/v1/assistants/mon-assistant/plan", json={"question": "Un conjoint de Français ?", "capacites_client": ["valider"]})
    assert p.status_code == 200, p.text
    plan = Plan.model_validate(p.json())
    assert plan.assistant == "mon-assistant" and plan.consigne == "pays-a-accord"
    e = appli.post("/api/v1/assistants/mon-assistant/executer", json={"question": "Un conjoint de Français ?"})
    assert e.status_code == 200 and Resultat.model_validate(e.json()).plan.assistant == "mon-assistant"
    modifie = {**p.json(), "etapes": p.json()["etapes"][:1], "consigne": None}
    e2 = appli.post("/api/v1/assistants/mon-assistant/executer", json={"question": "q", "plan": modifie})
    assert e2.json()["plan"]["etapes"] == modifie["etapes"], "un plan validé par le client est celui qui s'exécute"
    assert appli.post("/api/v1/assistants/mon-assistant/plan", json={"question": ""}).status_code == 422


def test_drapeau_faux_404(appli, capacites):
    capacites(assistants=False)
    assert appli.post("/api/v1/assistants/x-y-z/plan", json={"question": "q"}).status_code == 404


def test_non_montee_par_defaut(client):
    from app.config import settings

    assert settings.doublure_assistants is False
    assert client.post("/api/v1/assistants/x-y-z/plan", json={"question": "q"}).status_code == 404
    chemins = {getattr(r, "path", "") for r in client.app.routes}
    assert not any(c.startswith("/api/v1/assistants") for c in chemins)
