"""La doublure du harnais (ADR-0003) : `POST /api/v1/assistants/{id}/plan` et `/executer`
rendent un plan et un résultat CONFORMES AU CONTRAT, lus dans app/doublure/assistants/. Pour
que l'interface des assistants (lot B) avance sans le harnais (lot A).

Montée seulement si MYCOLLECTIONS_DOUBLURE_ASSISTANTS=true (défaut : non). Les vraies routes
(routers/assistants.py) servent les mêmes adresses et les mêmes corps ; quand la doublure est
demandée elles lui passent la main, de sorte que les prévisualisations restent montrables.
Chaque réponse de la doublure porte l'en-tête `X-Mycollections-Doublure: 1`, que l'interface
lit pour dire que le moteur n'est pas branché."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from fastapi import APIRouter, Depends, Response

from app.harnais.contrat import Plan, Resultat
from app.routers._commun import capacite
from app.routers.assistants import ENTETE_DOUBLURE, DemandeExecution, DemandePlan

REP = Path(__file__).resolve().parents[1] / "doublure" / "assistants"

router = APIRouter(prefix="/api/v1/assistants", tags=["assistants (doublure)"], dependencies=[Depends(capacite("assistants"))])


@cache
def _lire(nom: str) -> dict:
    return json.loads((REP / nom).read_text(encoding="utf-8"))


def _plan_pour(ident: str) -> Plan:
    return Plan.model_validate({**_lire("plan.json"), "assistant": ident})


@router.post("/{ident}/plan")
async def plan(ident: str, demande: DemandePlan, response: Response) -> Plan:
    response.headers[ENTETE_DOUBLURE] = "1"
    return _plan_pour(ident)


@router.post("/{ident}/executer")
async def executer(ident: str, demande: DemandeExecution, response: Response) -> Resultat:
    response.headers[ENTETE_DOUBLURE] = "1"
    resultat = Resultat.model_validate(_lire("resultat.json"))
    return resultat.model_copy(update={"plan": demande.plan or _plan_pour(ident)})
