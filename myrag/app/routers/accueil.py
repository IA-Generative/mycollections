"""L'accueil : ce que mes collections ont rendu possible, et une collection à essayer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.routers._collectif_commun import Identite, identite
from app.services import accueil

router = APIRouter(prefix="/api/accueil", tags=["accueil"])


@router.get("/mes-collections")
async def mes_collections(moi: Identite = Depends(identite)):
    return await accueil.mes_collections(moi.user.sub, moi.hash)


@router.get("/exemple")
async def exemple(sauf: str | None = Query(None, max_length=255), moi: Identite = Depends(identite)):
    return {"exemple": await accueil.exemple(moi.user.groups, moi.user.sub, sauf)}
