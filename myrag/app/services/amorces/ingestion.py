"""Ingérer les documents d'une amorce — de façon idempotente.

Un document se reconnaît à son nom et à son empreinte : même nom, même empreinte,
même découpage, on passe ; sinon c'est une nouvelle version (l'ancienne ligne est
mise à jour, le fichier réécrit). Chaque document part ENTIER vers OpenRAG, qui
le découpe (ADR-0005) : plus de morceaux situés à la main — le chunker d'OpenRAG
préfixe chaque passage de son chemin de titres, et les titres des amorces (une
ligne `# …` en tête de document) deviennent des titres de section reconnus.

⚠ OpenRAG ne sait pas retirer les morceaux d'un document : une nouvelle version
AJOUTE ses morceaux à côté des anciens. Pour repartir propre, `purger()` vide la
partition et oublie les documents connus — tout se réindexe au prochain import.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from app.database import async_session
from app.models.db import SourceFile, utcnow
from app.services.chunker import Sensitivity
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.amorces")

#: Change quand la façon d'ingérer change (aujourd'hui : document entier à OpenRAG,
#: ADR-0005) : tout document déjà connu repasse en « nouvelle version » au prochain
#: import, sans purge.
VERSION_DECOUPAGE = 1
ETIQUETTE = f"openrag-v{VERSION_DECOUPAGE}"


@dataclass
class Document:
    nom: str  # nom de fichier stable (clé d'idempotence)
    texte: str
    metadonnees: dict = field(default_factory=dict)


class Bilan(BaseModel):
    """Ce qu'un import a fait : documents indexés, ignorés (déjà là), échecs, versions."""

    documents: int = 0
    ignores: int = 0
    echecs: int = 0
    versions: int = 0


class BilanPurge(BaseModel):
    """Ce qu'une purge a oublié : les documents connus repartent pour réindexation."""

    documents_oublies: int = 0


def _sauver(collection: str, nom: str, contenu: bytes) -> str:
    from app.routers.ingest import _save_source_file

    return _save_source_file(collection, nom, contenu)


async def _envoyer(client: OpenRAGClient, collection: str, doc: Document, contenu: bytes) -> str | None:
    """Confie le document à OpenRAG et suit sa tâche d'indexation jusqu'au bout : rend
    None s'il est indexé, la raison sinon. Même règle que le dépôt (travaux) : rien
    n'est marqué réussi tant qu'OpenRAG n'a pas fini de lire — et un 409 (« déjà là »)
    est réussi, comme au dépôt : un import arrêté avant sa dernière écriture ne doit
    pas réessayer pour toujours ce qu'OpenRAG a déjà indexé."""
    import httpx

    from app.routers.ingest import attendre_indexation

    try:
        envoi = await client.upload_document(collection, doc.nom, contenu, "text/markdown", metadata={"title": doc.nom, "sensitivity": Sensitivity.PUBLIC})
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 409:
            return None
        raise
    return await attendre_indexation(client, envoi, doc.nom)


async def purger(collection: str) -> BilanPurge:
    """Vider la partition OpenRAG et oublier les documents connus : le prochain
    import réindexe tout, proprement. Les fichiers sources sur disque restent."""
    client = OpenRAGClient(timeout=120.0)
    await client.delete_partition(collection)
    await client.create_partition(collection)
    async with async_session() as session:
        r = await session.execute(delete(SourceFile).where(SourceFile.collection_name == collection))
        await session.commit()
    oublies = r.rowcount if isinstance(r, CursorResult) else 0
    logger.info("amorce %s : partition purgée, %d documents oubliés", collection, oublies)
    return BilanPurge(documents_oublies=oublies)


async def ingerer(collection: str, documents: list[Document], *, max_documents: int | None = None) -> Bilan:
    """Rend un bilan chiffré : documents indexés, ignorés (déjà là), échecs, versions."""
    bilan = Bilan()
    client = OpenRAGClient(timeout=120.0)
    try:
        await client.create_partition(collection)
    except Exception:  # noqa: BLE001 — la partition existe peut-être, ou OpenRAG dira non à l'envoi
        pass

    async with async_session() as session:
        lignes = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection))).scalars().all()
        connus: dict[str, SourceFile | None] = {sf.filename: sf for sf in lignes}

        for doc in documents:
            if max_documents is not None and bilan.documents >= max_documents:
                break
            contenu = doc.texte.encode("utf-8")
            empreinte = hashlib.sha256(contenu).hexdigest()
            existant = connus.get(doc.nom)
            if existant and existant.checksum == empreinte and existant.strategy_used == ETIQUETTE:
                bilan.ignores += 1
                continue
            chemin = _sauver(collection, doc.nom, contenu)
            try:
                erreur = await _envoyer(client, collection, doc, contenu)
            except Exception as e:  # noqa: BLE001 — on compte, on continue
                erreur = str(e) or type(e).__name__  # une exception sans message compte aussi
            if erreur:
                # Rien n'est marqué — ni empreinte, ni étiquette : le prochain import
                # réessaie ce document au lieu de l'ignorer pour toujours.
                bilan.echecs += 1
                logger.warning("amorce %s : « %s » non indexé (%s)", collection, doc.nom, erreur)
                continue
            if existant:
                existant.checksum, existant.storage_path = empreinte, chemin
                existant.file_size, existant.chunks_produced = len(contenu), 0
                existant.strategy_used, existant.last_indexed_at = ETIQUETTE, utcnow()
                existant.sensitivity = Sensitivity.PUBLIC
                bilan.versions += 1
            else:
                session.add(
                    SourceFile(
                        collection_name=collection,
                        filename=doc.nom,
                        original_url=doc.metadonnees.get("url", ""),
                        storage_path=chemin,
                        file_size=len(contenu),
                        content_type="text/markdown",
                        checksum=empreinte,
                        strategy_used=ETIQUETTE,
                        chunks_produced=0,
                        sensitivity=Sensitivity.PUBLIC,
                        last_indexed_at=utcnow(),
                    )
                )
                connus[doc.nom] = None
            bilan.documents += 1
        await session.commit()
    return bilan
