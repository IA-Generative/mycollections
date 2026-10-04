"""Dépendances de droits par collection, pour les routes dont la collection est dans le chemin.

Même règle que la publication (`publication._fiche_pour`) : lire = la portée de la fiche le
permet (404 sinon, sans dire que la collection existe) ; gérer = créateur, groupe
`<racine>/<nom>-admin` ou administrateur (403 pour qui lit seulement).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.auth import CurrentUser, current_user
from app.services import access


async def lire_la_collection(collection: str, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    from app.routers.publication import _fiche_pour
    await _fiche_pour(collection, user, ecrire=False)
    return user


async def gerer_la_collection(collection: str, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    from app.routers.publication import _fiche_pour
    await _fiche_pour(collection, user, ecrire=True)
    return user


async def exiger_administration(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not access.is_superadmin(user.groups):
        raise HTTPException(status_code=403, detail="Geste réservé à l'administration")
    return user


async def peut_lire_nom(collection: str, user: CurrentUser) -> bool:
    from app.routers.publication import _fiche_pour
    try:
        await _fiche_pour(collection, user, ecrire=False)
        return True
    except HTTPException:
        return False
