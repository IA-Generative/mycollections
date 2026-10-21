"""Les droits sur un assistant, calculés du jeton et des collections de la fiche — jamais d'un
paramètre du client. Partagé par le routeur de la fiche et par la recherche par assistant."""

from __future__ import annotations

from app.auth import CurrentUser
from app.harnais.contrat import FicheAssistant
from app.services import access
from app.services.collection_store import get_collection


async def collections_de(fiche: FicheAssistant) -> dict[str, dict | None]:
    return {s.id: await get_collection(s.id) for s in fiche.sources if s.type == "collection"}


def lisible(col: dict | None, user: CurrentUser) -> bool:
    if not col or col.get("archived_at"):
        return False
    return access.can_read(name=col["name"], scope=col["scope"], scope_groups=col["scope_groups"], created_by=col["created_by"], user_groups=user.groups, user_sub=user.sub)


def gerable(col: dict | None, user: CurrentUser) -> bool:
    return bool(col) and access.can_write(name=col["name"], created_by=col["created_by"], user_groups=user.groups, user_sub=user.sub)


async def droits(fiche: FicheAssistant, createur_hash: str | None, *, user: CurrentUser, hash_: str, superadmin: bool) -> tuple[bool, bool, dict[str, dict | None]]:
    """(voir, modifier, collections) pour cette fiche et cette personne."""
    cols = await collections_de(fiche)
    createur = bool(createur_hash) and createur_hash == hash_
    if superadmin:
        return True, True, cols
    voir = createur or any(lisible(c, user) for c in cols.values())
    # Une collection supprimée ne retient plus rien : on juge sur celles qui existent encore. Sans
    # aucune (toutes supprimées), l'assistant revient à qui l'a créé, sans quoi personne hors
    # administration ne pourrait plus le retirer.
    presentes = [c for c in cols.values() if c is not None]
    modifier = all(gerable(c, user) for c in presentes) if presentes else createur
    return voir, modifier, cols
