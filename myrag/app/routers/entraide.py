"""Le réseau d'entraide (lot G du chantier des assistants de recherche) : appels à l'aide,
recommandations, réponses. Routeur vide au lot 0, déjà monté et gardé par le drapeau
`entraide` : le lot G le remplit sans toucher `main.py`. Module détachable : routes, tables
(`app/models/entraide.py`) et pages sous un seul préfixe, aucune dépendance entrante."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers._commun import capacite

router = APIRouter(prefix="/api/entraide", tags=["entraide"], dependencies=[Depends(capacite("entraide"))])
