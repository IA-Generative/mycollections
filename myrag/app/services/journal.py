"""Le fil d'avancement : chaque route qui change quelque chose écrit ici, dans la
MÊME transaction que le changement — un geste sans trace n'a pas eu lieu.

Un événement est signé d'une personne (condensé) OU d'un robot, jamais des deux,
jamais aucun : la table le vérifie. Le détail est chiffré (lignes importées,
fichiers, questions testées, taux), pas narratif.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Evenement

LIMITE_DEFAUT = 50
LIMITE_MAX = 200


def ecrire(
    session: AsyncSession,
    objet_type: str,
    objet_id: str,
    type_: str,
    *,
    auteur_hash: str | None = None,
    robot: str | None = None,
    collection_name: str | None = None,
    detail: dict | None = None,
) -> Evenement:
    if bool(auteur_hash) == bool(robot):
        raise ValueError("un événement est signé d'une personne OU d'un robot")
    ev = Evenement(
        objet_type=objet_type,
        objet_id=str(objet_id),
        collection_name=collection_name,
        type=type_,
        auteur_hash=auteur_hash,
        robot=robot,
        detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
    )
    session.add(ev)
    return ev


async def lire(
    session: AsyncSession,
    objet_type: str,
    objet_id: str,
    *,
    limite: int = LIMITE_DEFAUT,
    avant: datetime | None = None,
) -> tuple[list[Evenement], datetime | None]:
    """Les événements d'un objet, du plus récent au plus ancien, paginés par date."""
    limite = max(1, min(int(limite), LIMITE_MAX))
    stmt = (
        select(Evenement)
        .where(Evenement.objet_type == objet_type, Evenement.objet_id == str(objet_id))
        .order_by(Evenement.cree_le.desc(), Evenement.id.desc())
        .limit(limite + 1)
    )
    if avant is not None:
        stmt = stmt.where(Evenement.cree_le < avant)
    lignes = list((await session.execute(stmt)).scalars().all())
    suivant = None
    if len(lignes) > limite:
        lignes = lignes[:limite]
        suivant = lignes[-1].cree_le
    return lignes, suivant


async def derniers_par_objet(session: AsyncSession, objet_type: str) -> dict[str, datetime]:
    """Pour chaque objet du type, la date de son dernier événement (calcul du sommeil)."""
    stmt = (
        select(Evenement.objet_id, func.max(Evenement.cree_le))
        .where(Evenement.objet_type == objet_type)
        .group_by(Evenement.objet_id)
    )
    return {objet_id: date for objet_id, date in (await session.execute(stmt)).all()}
