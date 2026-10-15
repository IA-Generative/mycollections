"""Remplacé par le jeu de questions de référence (docs/qualite.md) : les jeux de test (EvalDataset).

Les routes répondent 410 et disent où aller. Elles disparaîtront à la version suivante.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/eval", tags=["Eval"])

_DETAIL = "Remplacé par /api/collections/{collection}/qualite/questions (jeu de questions de référence)."


@router.api_route("/{collection}{reste:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def remplace(collection: str, reste: str = ""):
    raise HTTPException(status_code=410, detail=_DETAIL)
