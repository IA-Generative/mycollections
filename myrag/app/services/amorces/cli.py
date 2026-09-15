"""Import d'une amorce depuis la ligne de commande — depuis le pod, sans passer par
l'API : `python -m app.services.amorces.cli natinf [--max-documents N] [--purger]`.

Même code que la route (préparation, connecteur, couverture, journal) ; rejouable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _jouer(ident: str, max_documents: int | None, purger: bool = False) -> int:
    from app.amorces import entree
    from app.database import init_db
    from app.routers.amorces import _executer, _preparer
    from app.services import collectif_store as store
    import app.models.db  # noqa: F401 — enregistre les tables

    e = entree(ident)
    if not e:
        print(f"amorce inconnue : {ident}", file=sys.stderr)
        return 2
    if max_documents is not None:
        e.setdefault("parametres", {})["max_documents"] = max_documents
    await init_db()
    name = await _preparer(e)
    await store.marquer_amorce(ident, "en_cours", collection_name=name)
    if purger:
        from app.services.amorces import ingestion
        await ingestion.purger(name)
        await store.consigner("collection", name, "import.purge", robot=f"amorce:{ident}", collection_name=name)
    try:
        resultat = await _executer(ident, e, name, depuis_zero=purger)
    except Exception as ex:  # noqa: BLE001
        print(f"échec : {ex}", file=sys.stderr)
        return 1
    print(json.dumps({"amorce": ident, "collection": name, **resultat}, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Importer une amorce du catalogue")
    p.add_argument("amorce")
    p.add_argument("--max-documents", type=int, default=None)
    p.add_argument("--purger", action="store_true", help="vider la partition et réindexer tout")
    args = p.parse_args()
    sys.exit(asyncio.run(_jouer(args.amorce, args.max_documents, args.purger)))


if __name__ == "__main__":
    main()
