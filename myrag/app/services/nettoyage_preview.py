"""Fin d'une preview : supprimer chez OpenRAG les partitions qu'elle a créées.

Une preview partage l'OpenRAG de la bêta ; ses partitions portent toutes son préfixe
(`MYCOLLECTIONS_PARTITION_PREFIXE`, imposé par openrag_client). Sans ce nettoyage, chaque PR
fermée laisserait ses partitions derrière elle.

Lancé par le chart (Job `PreDelete`) : `python -m app.services.nettoyage_preview`.
Ne fait RIEN sans préfixe — jamais sur la bêta — et ne fait jamais échouer la suppression de
la preview (code 0 même en cas d'erreur : un nettoyage raté ne doit pas la bloquer).
"""

import asyncio
import logging

from app.config import settings
from app.services.collection_store import list_collections
from app.services.openrag_client import OpenRAGClient, PartitionHorsPerimetre

logger = logging.getLogger("myrag.nettoyage_preview")


async def nettoyer() -> list[str]:
    prefixe = (settings.partition_prefixe or "").strip().lower()
    if not prefixe:
        logger.warning("nettoyage de preview ignoré : aucun préfixe de partition (pas une preview)")
        return []
    client = OpenRAGClient(timeout=30.0)
    supprimees = []
    for col in await list_collections(include_archived=True):
        nom = col.get("name", "")
        if not nom.lower().startswith(prefixe):
            continue
        try:
            await client.delete_partition(nom)
            supprimees.append(nom)
        except PartitionHorsPerimetre:
            continue
        except Exception as e:  # noqa: BLE001 — on poursuit avec les suivantes
            logger.error("partition %s non supprimée : %s", nom, e)
    logger.info("nettoyage de preview : %d partition(s) supprimée(s)", len(supprimees))
    return supprimees


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(nettoyer())
    except Exception as e:  # noqa: BLE001
        logger.error("nettoyage de preview interrompu : %s", e)
