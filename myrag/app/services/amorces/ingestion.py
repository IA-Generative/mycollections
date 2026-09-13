"""Ingérer les documents d'une amorce — de façon idempotente.

Un document se reconnaît à son nom et à son empreinte : même nom, même empreinte,
on passe ; même nom, empreinte différente, c'est une nouvelle version (l'ancienne
ligne est mise à jour, le fichier réécrit). Les morceaux partent vers OpenRAG un
par un, dans l'ordre, sans tâche de fond : ce qui est compté a été envoyé.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from sqlalchemy import select

from app.database import async_session
from app.models.db import SourceFile, utcnow
from app.services.chunker import chunk_document
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.amorces")


@dataclass
class Document:
    nom: str            # nom de fichier stable (clé d'idempotence)
    texte: str
    metadonnees: dict = field(default_factory=dict)


def _sauver(collection: str, nom: str, contenu: bytes) -> str:
    from app.routers.ingest import _save_source_file
    return _save_source_file(collection, nom, contenu)


async def ingerer(collection: str, documents: list[Document], *, strategie: str = "section",
                  max_documents: int | None = None) -> dict:
    """Rend un bilan chiffré : documents envoyés, ignorés (déjà là), morceaux, échecs."""
    bilan = {"documents": 0, "ignores": 0, "morceaux": 0, "echecs": 0, "versions": 0}
    client = OpenRAGClient(timeout=120.0)
    try:
        await client.create_partition(collection)
    except Exception:  # noqa: BLE001 — la partition existe peut-être, ou OpenRAG dira non à l'envoi
        pass

    async with async_session() as session:
        lignes = (await session.execute(
            select(SourceFile).where(SourceFile.collection_name == collection)
        )).scalars().all()
        connus = {sf.filename: sf for sf in lignes}

        for doc in documents:
            if max_documents is not None and bilan["documents"] >= max_documents:
                break
            contenu = doc.texte.encode("utf-8")
            empreinte = hashlib.sha256(contenu).hexdigest()
            existant = connus.get(doc.nom)
            if existant and existant.checksum == empreinte:
                bilan["ignores"] += 1
                continue
            morceaux = chunk_document(doc.texte, strategy=strategie, sensitivity="public")
            if not morceaux:
                continue
            chemin = _sauver(collection, doc.nom, contenu)
            echecs = 0
            for m in morceaux:
                m.setdefault("filename", doc.nom)
                try:
                    await client.upload_chunk(collection, m)
                except Exception as e:  # noqa: BLE001 — on compte, on continue
                    echecs += 1
                    logger.warning("amorce %s : morceau refusé (%s)", collection, e)
            if existant:
                existant.checksum, existant.storage_path = empreinte, chemin
                existant.file_size, existant.chunks_produced = len(contenu), len(morceaux)
                existant.last_indexed_at = utcnow()
                bilan["versions"] += 1
            else:
                session.add(SourceFile(
                    collection_name=collection, filename=doc.nom, original_url=doc.metadonnees.get("url", ""),
                    storage_path=chemin, file_size=len(contenu), content_type="text/markdown",
                    checksum=empreinte, strategy_used=strategie, chunks_produced=len(morceaux),
                    last_indexed_at=utcnow(),
                ))
                connus[doc.nom] = None  # type: ignore[assignment]
            bilan["documents"] += 1
            bilan["morceaux"] += len(morceaux)
            bilan["echecs"] += echecs
        await session.commit()
    return bilan
