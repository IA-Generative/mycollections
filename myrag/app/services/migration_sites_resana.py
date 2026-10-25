"""Au démarrage : les collections Résana importées avant que l'adresse commune de leurs documents
ne devienne leur source et un site déclaré du plug-in (#169) sont rattrapées. Idempotent : la
source n'est posée que si elle est vide, le site n'est ajouté que s'il manque, rien n'écrase une
saisie."""

from __future__ import annotations

import logging

from app.services import sources_url
from app.services.collection_store import get_source_config, list_collections, update_collection

logger = logging.getLogger("myrag.demarrage")


async def proposer_les_sites_resana() -> dict:
    bilan = {"collections": 0, "sources": 0, "sites": 0}
    for col in await list_collections(include_archived=True):
        if col.get("source_type") != "resana":
            continue
        bilan["collections"] += 1
        try:
            cfg = await get_source_config(col["name"])
            motif = sources_url.prefixe_commun([str(v.get("url") or "") for v in (cfg.get("documents") or {}).values()])
            if not motif:
                continue
            if not (col.get("source_url") or "").strip():
                await update_collection(col["name"], {"source_url": motif.removesuffix("*")})
                bilan["sources"] += 1
            if motif not in await sources_url.ajouter_sites(col["name"], []):
                await sources_url.ajouter_sites(col["name"], [motif])
                bilan["sites"] += 1
        except Exception as e:  # noqa: BLE001 — une collection en faute n'empêche pas les autres
            logger.warning("résana %s : site non rattrapé (%s)", col["name"], type(e).__name__)
    return bilan
