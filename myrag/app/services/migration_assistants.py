"""Chaque collection publiée devient un assistant de recherche à une source (ADR-0003), au
démarrage, sans jamais rien créer deux fois : `assistants.collection_name` est la clé
d'idempotence (comme `paire_qa.source_ref` pour le jeu de questions). Une collection dépubliée
ou archivée voit son miroir mis en sommeil ; republiée, il se réveille. Rien n'est effacé ici.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.database import async_session
from app.models.db import Collection
from app.services import assistant_store

logger = logging.getLogger("myrag.assistants")

ISSUES = ("cree", "inchange", "archive", "reactive", "hors_critere", "invalide", "erreur")


async def migrer_collections_publiees() -> dict:
    """Un passage sur toutes les collections ; ne lève jamais (un démarrage ne doit pas tomber)."""
    bilan = dict.fromkeys(ISSUES, 0)
    async with async_session() as s:
        noms = (await s.execute(select(Collection.name).order_by(Collection.name))).scalars().all()
    for name in noms:
        try:
            bilan[await assistant_store.assurer_miroir(name)] += 1
        except Exception as e:  # noqa: BLE001 — une collection en faute n'arrête pas les autres
            logger.error("assistant miroir de %s : %s", name, e)
            bilan["erreur"] += 1
    if bilan["cree"] or bilan["archive"] or bilan["reactive"] or bilan["erreur"]:
        logger.info("assistants dérivés des collections : %s", bilan)
    return bilan
