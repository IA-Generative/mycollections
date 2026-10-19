"""La doublure du harnais (ADR-0003) : `POST /api/v1/assistants/{id}/plan` et `/executer`
rendent un plan et un résultat CONFORMES AU CONTRAT, lus dans app/doublure/assistants/. Pour
que l'interface des assistants (lot B) avance sans le harnais (lot A).

Montée seulement si MYCOLLECTIONS_DOUBLURE_ASSISTANTS=true (défaut : non). Le lot A la retire
quand il sert les vraies routes, sous les mêmes adresses et les mêmes corps."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.harnais.contrat import Plan, Resultat
from app.routers._commun import capacite

REP = Path(__file__).resolve().parents[1] / "doublure" / "assistants"

router = APIRouter(prefix="/api/v1/assistants", tags=["assistants (doublure)"], dependencies=[Depends(capacite("assistants"))])


class DemandePlan(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    capacites_client: list[str] = Field(default_factory=list)


class DemandeExecution(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    plan: Plan | None = None


@cache
def _lire(nom: str) -> dict:
    return json.loads((REP / nom).read_text(encoding="utf-8"))


def _plan_pour(ident: str) -> Plan:
    return Plan.model_validate({**_lire("plan.json"), "assistant": ident})


@router.post("/{ident}/plan")
async def plan(ident: str, demande: DemandePlan) -> Plan:
    return _plan_pour(ident)


@router.post("/{ident}/executer")
async def executer(ident: str, demande: DemandeExecution) -> Resultat:
    resultat = Resultat.model_validate(_lire("resultat.json"))
    return resultat.model_copy(update={"plan": demande.plan or _plan_pour(ident)})
