"""Ce que partagent les routeurs du collectif : identité condensée, capacités,
collection lisible, garant."""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException, Query

from app.auth import CurrentUser, current_user
from app.services import access, capacites
from app.services import collectif_store as store
from app.services.pseudo import SelAbsent, condenser


class Identite:
    __slots__ = ("user", "hash", "superadmin")

    def __init__(self, user: CurrentUser, hash_: str):
        self.user = user
        self.hash = hash_
        self.superadmin = access.is_superadmin(user.groups)


async def identite(user: CurrentUser = Depends(current_user)) -> Identite:
    try:
        return Identite(user, condenser(user.sub))
    except SelAbsent:
        raise HTTPException(status_code=503, detail="Le service n'est pas configuré pour le collectif (sel des identités absent)")
    except ValueError:
        raise HTTPException(status_code=401, detail="Jeton sans identité exploitable")


def capacite(nom: str):
    async def _dep() -> None:
        if (await capacites.lire_async()).get(nom) is not True:
            raise HTTPException(status_code=404, detail=f"Fonction désactivée : « {nom} » n'est pas déclarée dans capacites.json")
    return _dep


async def collection_lisible(name: str, moi: Identite = Depends(identite)) -> dict:
    """La fiche brute si l'appelant peut la lire ; 404 sinon (ne pas divulguer l'existence)."""
    try:
        f = await store.fiche(name)
    except store.Introuvable:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    if not access.can_read(name=name, scope=f["scope"], scope_groups=f["scope_groups"],
                           created_by=f["created_by"], user_groups=moi.user.groups, user_sub=moi.user.sub):
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return f


def est_garant(f: dict, moi: Identite) -> bool:
    return moi.superadmin or (bool(f.get("garant_hash")) and f["garant_hash"] == moi.hash)


def exiger_garant(f: dict, moi: Identite) -> None:
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
