"""Ce qui se joue au démarrage, après la création des tables : les migrations idempotentes,
dans l'ordre. Un lot qui en ajoute une l'ajoute à `MIGRATIONS` — pas au lifespan de `main.py`.
Chacune est jouée sous garde : une migration en faute se journalise, les suivantes se jouent."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.services.migration_assistants import migrer_collections_publiees
from app.services.migration_questions import migrer_vers_questions

logger = logging.getLogger("myrag.demarrage")

MIGRATIONS: tuple[Callable[[], Awaitable[dict]], ...] = (
    migrer_vers_questions,  # docs/qualite.md : les anciens magasins versés dans le jeu de questions
    migrer_collections_publiees,  # ADR-0003 : une collection publiée a son assistant à une source
)


async def migrations_au_demarrage() -> dict:
    bilan: dict[str, object] = {}
    for migration in MIGRATIONS:
        try:
            bilan[migration.__name__] = await migration()
        except Exception as e:  # noqa: BLE001
            logger.error("migration %s : %s", migration.__name__, e)
            bilan[migration.__name__] = "erreur"
    return bilan
