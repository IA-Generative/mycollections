"""La route compatible OpenAI des assistants (lot A, pas 7) : modèles `assistant-<id>`,
réponse composée avec les règles « répondre » et un bloc « Comment j'ai cherché ». Routeur
vide au lot 0, déjà monté (jeton exigé) et gardé par le drapeau `assistants`."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers._commun import capacite

router = APIRouter(prefix="/v1", tags=["openai"], dependencies=[Depends(capacite("assistants"))])
