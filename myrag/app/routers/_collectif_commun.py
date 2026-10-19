"""Ce que partagent les routeurs du collectif : collection lisible, garant, pagination. L'identité,
l'administration et les capacités viennent de `_commun` (ré-exportées ici)."""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException, Query

from app.models.collectif import FicheCollection
from app.routers._commun import Identite, capacite, exiger_superadmin, identite
from app.services import access
from app.services import collectif_store as store

__all__ = ["Identite", "capacite", "collection_lisible", "date_avant", "est_garant", "exiger_garant", "exiger_superadmin", "identite", "limite"]


async def collection_lisible(name: str, moi: Identite = Depends(identite)) -> FicheCollection:
    """La fiche brute si l'appelant peut la lire ; 404 sinon (ne pas divulguer l'existence)."""
    try:
        f = await store.fiche(name)
    except store.Introuvable:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    if not access.can_read(name=name, scope=f.scope, scope_groups=f.scope_groups, created_by=f.created_by, user_groups=moi.user.groups, user_sub=moi.user.sub):
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return f


def est_garant(f: FicheCollection, moi: Identite) -> bool:
    return moi.superadmin or (bool(f.garant_hash) and f.garant_hash == moi.hash)


def exiger_garant(f: FicheCollection, moi: Identite) -> None:
    if not est_garant(f, moi):
        raise HTTPException(status_code=403, detail="Geste réservé au garant de la collection")


def date_avant(avant: str | None = Query(None)) -> datetime | None:
    if not avant:
        return None
    try:
        return datetime.fromisoformat(avant)
    except ValueError:
        raise HTTPException(status_code=422, detail="`avant` doit être une date ISO 8601")


def limite(limite: int = Query(50, ge=1, le=200)) -> int:
    return limite
