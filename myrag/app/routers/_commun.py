"""Ce que partagent les routeurs, au-delà du collectif : l'identité condensée de l'appelant, le
geste réservé à l'administration, et la capacité déclarée par le menu commun (404 sinon).
`_collectif_commun` les ré-exporte : les routeurs existants n'ont pas changé d'import."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.auth import CurrentUser, current_user
from app.services import access, capacites
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


async def exiger_superadmin(moi: Identite = Depends(identite)) -> Identite:
    """Dépendance des gestes d'administration : 403 pour tout autre qu'un superadmin."""
    if not moi.superadmin:
        raise HTTPException(status_code=403, detail="Geste réservé à l'administration")
    return moi


def capacite(nom: str):
    """Un drapeau de capacites.json à `false` (ou absent) : la route n'existe pas (404)."""

    async def _dep() -> None:
        if (await capacites.lire_async()).get(nom) is not True:
            raise HTTPException(status_code=404, detail=f"Fonction désactivée : « {nom} » n'est pas déclarée dans capacites.json")

    return _dep
