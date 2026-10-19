"""Les passages qu'on donne à ragas : lus dans OpenRAG, échantillonnés, convertis en documents.

Chez Mes collections, un fichier d'OpenRAG EST un morceau du découpage (`upload_chunk`) ; une
collection importée par script peut, elle, avoir plusieurs morceaux par fichier. On prend donc
des FICHIERS en tourniquet (toute la collection est couverte, pas seulement le début de la liste),
puis un morceau par fichier, et un deuxième tour si cela ne suffit pas.

Chaque passage garde ses identifiants jusqu'à la paire générée : `chunk_id` (le morceau d'OpenRAG,
lisible par /api/openrag/extract/<id>, renouvelé à la réindexation) et `file_id` (le document,
ouvrable dans l'onglet Documents). Aucun texte de passage ne va dans les journaux.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import asdict, dataclass

from app.services import corpus
from app.services.morceau import decouper_morceau
from app.services.openrag_client import ExtraitOpenRAG, FichierOpenRAG, MorceauOpenRAG

logger = logging.getLogger("myrag.generation")

#: Un passage plus court ne porte pas assez de matière pour une question.
TEXTE_MIN = 40
FACTEUR = 4


@dataclass(frozen=True)
class Morceau:
    chunk_id: str
    file_id: str
    partition: str
    fichier: str
    page: str | None
    texte: str

    def identifiants(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "texte"}


def nombre_a_lire(taille: int, plafond: int) -> int:
    """4 passages par paire demandée, sans dépasser le plafond (ni descendre sous 1)."""
    return max(1, min(FACTEUR * max(1, int(taille)), max(1, int(plafond))))


def echantillonner_fichiers(fichiers: list[FichierOpenRAG], n: int, graine: str) -> list[FichierOpenRAG]:
    """`n` fichiers répartis sur toute la collection, dans l'ordre naturel des titres, à pas
    régulier depuis un départ tiré de la graine (même graine ⇒ même échantillon). Tous si moins."""
    valides = [f for f in fichiers if f.file_id]
    valides.sort(key=lambda f: (corpus._cle_naturelle(str(f.title or f.original_filename or f.filename or "")), str(f.file_id)))
    if len(valides) <= n:
        return valides
    pas = len(valides) / n
    depart = random.Random(graine).random() * pas
    return [valides[int(depart + i * pas)] for i in range(n)]


def _meta(brut: MorceauOpenRAG | ExtraitOpenRAG) -> dict:
    """Les métadonnées d'un morceau OpenRAG, ou un dictionnaire vide."""
    return brut.metadata if isinstance(brut.metadata, dict) else {}


def _texte_chunk(brut: MorceauOpenRAG) -> str:
    return str(brut.content or _meta(brut).get("content") or "")


def _texte_extrait(brut: ExtraitOpenRAG) -> str:
    return str(brut.page_content or _meta(brut).get("content") or "")


def _page(meta: dict) -> str | None:
    page = meta.get("page")
    return None if page in ("", None) else str(page)


def morceau_depuis_chunk(brut: MorceauOpenRAG, partition: str) -> Morceau | None:
    """Un élément de `GET /partition/<p>/chunks`. None s'il est vide, trop court, ou d'ailleurs."""
    meta = _meta(brut)
    if meta.get("partition") not in (None, partition):
        return None
    chunk_id = str(meta.get("_id") or "")
    if not chunk_id:
        lien = str(brut.link or "")
        chunk_id = lien.rsplit("/extract/", 1)[-1].split("?")[0] if "/extract/" in lien else ""
    _ctx, fichier_balise, corps = decouper_morceau(_texte_chunk(brut))
    if not chunk_id or len(corps) < TEXTE_MIN:
        return None
    fichier = str(meta.get("original_filename") or meta.get("filename") or fichier_balise or "")
    return Morceau(chunk_id, str(meta.get("file_id") or ""), partition, fichier, _page(meta), corps)


def morceau_depuis_extrait(chunk_id: str, file_id: str, partition: str, brut: ExtraitOpenRAG | None) -> Morceau | None:
    """Un `GET /extract/<id>` (repli des instances sans /chunks)."""
    if brut is None:
        return None
    meta = _meta(brut)
    if meta.get("partition") not in (None, partition):
        return None
    _ctx, fichier_balise, corps = decouper_morceau(_texte_extrait(brut))
    if len(corps) < TEXTE_MIN:
        return None
    fichier = str(meta.get("original_filename") or meta.get("filename") or fichier_balise or "")
    return Morceau(str(chunk_id), str(file_id), partition, fichier, _page(meta), corps)


async def _morceaux_du_fichier(client, partition: str, file_id: str) -> list[Morceau]:
    brut = await client.partition_chunks(partition, file_id=file_id)
    if brut is not None:
        return [m for m in (morceau_depuis_chunk(c, partition) for c in brut) if m]
    detail = await client.file_detail(partition, file_id)
    morceaux = []
    for cid in corpus.identifiants_des_morceaux(detail)[: corpus.MORCEAUX_MAX]:
        m = morceau_depuis_extrait(cid, file_id, partition, await client.extract(cid))
        if m:
            morceaux.append(m)
    return morceaux


async def lire_echantillon(client, partition: str, n: int, graine: str, parallelisme: int = 8) -> tuple[list[Morceau], int]:
    """(`n` passages au plus, nombre de fichiers de la collection). Un fichier illisible est
    sauté, jamais bloquant ; on reprend un deuxième passage par fichier si le premier tour manque."""
    fichiers = await corpus.fichiers_de(client, partition)
    choisis = echantillonner_fichiers(fichiers, n, graine)
    verrou = asyncio.Semaphore(parallelisme)
    illisibles = 0

    async def lire(f: FichierOpenRAG) -> list[Morceau]:
        nonlocal illisibles
        async with verrou:
            try:
                return await _morceaux_du_fichier(client, partition, str(f.file_id))
            except Exception as e:  # noqa: BLE001 — un fichier en panne ne fait pas échouer l'échantillon
                illisibles += 1
                logger.warning("génération : fichier illisible dans %s (%s)", partition, type(e).__name__)
                return []

    par_fichier = await asyncio.gather(*(lire(f) for f in choisis))
    hasard = random.Random(graine)
    for liste in par_fichier:
        hasard.shuffle(liste)
    pris: list[Morceau] = []
    vus: set[str] = set()
    tour = 0
    while len(pris) < n and any(len(lst) > tour for lst in par_fichier):
        for liste in par_fichier:
            if tour < len(liste) and liste[tour].chunk_id not in vus and len(pris) < n:
                pris.append(liste[tour])
                vus.add(liste[tour].chunk_id)
        tour += 1
    if illisibles:
        logger.info("génération : %d fichier(s) illisible(s) sur %d dans %s", illisibles, len(choisis), partition)
    return pris, len(fichiers)


def en_documents(morceaux: list[Morceau]) -> list:
    """Documents LangChain : le texte, et en métadonnées les identifiants qui doivent survivre
    au passage dans ragas pour remplir les contextes de référence de chaque paire."""
    from langchain_core.documents import Document

    return [Document(page_content=m.texte, metadata=m.identifiants()) for m in morceaux]
