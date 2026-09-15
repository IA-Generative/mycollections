"""Ingérer les documents d'une amorce — de façon idempotente.

Un document se reconnaît à son nom et à son empreinte : même nom, même empreinte,
même découpage, on passe ; sinon c'est une nouvelle version (l'ancienne ligne est
mise à jour, le fichier réécrit). Les morceaux partent vers OpenRAG un par un,
dans l'ordre, sans tâche de fond : ce qui est compté a été envoyé.

Chaque morceau est SITUÉ avant de partir : son texte commence par le titre du
document puis celui de sa section, et son nom de fichier porte le nom du document.
Sans cela, le découpage par section jetait le titre hors du texte indexé et
tronquait le nom à cinquante caractères : « Cambriolages — département 69 » et
« … — département 75 » devenaient le même morceau, sans département, et OpenRAG
refusait les doublons (NATINF : 8 879 morceaux sur 17 249 refusés en 409).

⚠ OpenRAG ne sait pas retirer les morceaux d'un document : une nouvelle version
AJOUTE ses morceaux à côté des anciens. Pour repartir propre, `purger()` vide la
partition et oublie les documents connus — tout se réindexe au prochain import.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select

from app.database import async_session
from app.models.db import SourceFile, utcnow
from app.services.chunker import chunk_document
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.amorces")

#: Change quand la façon de situer les morceaux change : tout document déjà connu
#: repasse alors en « nouvelle version » au prochain import, sans purge.
VERSION_DECOUPAGE = 2


@dataclass
class Document:
    nom: str            # nom de fichier stable (clé d'idempotence)
    texte: str
    metadonnees: dict = field(default_factory=dict)


def _sauver(collection: str, nom: str, contenu: bytes) -> str:
    from app.routers.ingest import _save_source_file
    return _save_source_file(collection, nom, contenu)


def _titre_du_document(texte: str) -> str:
    """La première ligne « # … » — le sujet du document (département, plage NATINF…)."""
    for ligne in texte.splitlines():
        if ligne.startswith("# "):
            return ligne[2:].strip()
    return ""


def _slug(texte: str, longueur: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texte.lower()).strip("-")[:longueur].strip("-")


def situer(doc: Document, morceaux: list[dict]) -> list[dict]:
    """Chaque morceau dit d'où il vient : titre du document, titre de sa section,
    nom de fichier dérivé du nom STABLE du document (jamais tronqué), numéroté
    pour que deux sections de même titre dans un document restent distinctes."""
    titre_doc = _titre_du_document(doc.texte) or doc.nom
    racine = doc.nom.rsplit(".", 1)[0]
    for i, m in enumerate(morceaux, 1):
        titre_section = (m.get("metadata") or {}).get("section_title", "") or ""
        entete = [f"# {titre_doc}"]
        if titre_section and titre_section != titre_doc:
            entete.append(f"## {titre_section}")
        m["content"] = "\n".join(entete) + "\n\n" + m["content"]
        slug = _slug(titre_section) if titre_section and titre_section != titre_doc else ""
        m["filename"] = f"{racine}--{i:03d}{'-' + slug if slug else ''}.md"
    return morceaux


def _etiquette(strategie: str) -> str:
    return f"{strategie}-v{VERSION_DECOUPAGE}"


async def purger(collection: str) -> dict:
    """Vider la partition OpenRAG et oublier les documents connus : le prochain
    import réindexe tout, proprement. Les fichiers sources sur disque restent."""
    from sqlalchemy import delete
    client = OpenRAGClient(timeout=120.0)
    await client.delete_partition(collection)
    await client.create_partition(collection)
    async with async_session() as session:
        r = await session.execute(delete(SourceFile).where(SourceFile.collection_name == collection))
        await session.commit()
    oublies = int(r.rowcount or 0)
    logger.info("amorce %s : partition purgée, %d documents oubliés", collection, oublies)
    return {"documents_oublies": oublies}


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
            if existant and existant.checksum == empreinte and existant.strategy_used == _etiquette(strategie):
                bilan["ignores"] += 1
                continue
            morceaux = situer(doc, chunk_document(doc.texte, strategy=strategie, sensitivity="public"))
            if not morceaux:
                continue
            chemin = _sauver(collection, doc.nom, contenu)
            echecs = 0
            for m in morceaux:
                try:
                    await client.upload_chunk(collection, m)
                except Exception as e:  # noqa: BLE001 — on compte, on continue
                    echecs += 1
                    logger.warning("amorce %s : morceau refusé (%s)", collection, e)
            if existant:
                existant.checksum, existant.storage_path = empreinte, chemin
                existant.file_size, existant.chunks_produced = len(contenu), len(morceaux)
                existant.strategy_used, existant.last_indexed_at = _etiquette(strategie), utcnow()
                bilan["versions"] += 1
            else:
                session.add(SourceFile(
                    collection_name=collection, filename=doc.nom, original_url=doc.metadonnees.get("url", ""),
                    storage_path=chemin, file_size=len(contenu), content_type="text/markdown",
                    checksum=empreinte, strategy_used=_etiquette(strategie), chunks_produced=len(morceaux),
                    last_indexed_at=utcnow(),
                ))
                connus[doc.nom] = None  # type: ignore[assignment]
            bilan["documents"] += 1
            bilan["morceaux"] += len(morceaux)
            bilan["echecs"] += echecs
        await session.commit()
    return bilan
