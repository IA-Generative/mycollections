"""Ingest router — async upload + intelligent chunking + OpenRAG indexing."""

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import CurrentUser, current_user
from app.config import settings
from app.security_utils import assert_public_http_url, ensure_within, safe_filename, ssrf_request_guard
from app.services import formats
from app.services.chunker import Sensitivity, Strategy, chunk_document, valider_sensibilite, valider_strategy
from app.services.job_store import complete_job, create_job, get_job, increment_job_progress, list_jobs, update_job
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])
logger = logging.getLogger("myrag.ingest")

# R7 — Source file storage directory
SOURCES_DIR = Path(settings.data_dir) / "_sources"


def _save_source_file(collection: str, filename: str, content: bytes) -> str:
    """Save source file to disk for re-indexation (R7). Returns the storage path.

    `collection` et `filename` proviennent d'entrées utilisateur : on confine
    le chemin sous SOURCES_DIR et on réduit le filename à un basename sûr pour
    empêcher toute traversée de répertoire.
    """
    filename = safe_filename(filename)
    col_dir = ensure_within(SOURCES_DIR, SOURCES_DIR / collection)
    col_dir.mkdir(parents=True, exist_ok=True)
    path = ensure_within(col_dir, col_dir / filename)
    path.write_bytes(content)
    return str(path)


async def _upload_chunks_background(job_id: str, collection: str, chunks: list[dict]):
    """Background task: upload chunks to OpenRAG, updating job progress in DB."""
    client = OpenRAGClient(timeout=120.0)

    await update_job(job_id, status="uploading")

    for i, chunk in enumerate(chunks):
        success = True
        try:
            await client.upload_chunk(collection, chunk)
        except httpx.HTTPStatusError as e:
            # 409 : OpenRAG a déjà ce morceau, à l'identique (dépôt répété, reprise après arrêt).
            if e.response is None or e.response.status_code != 409:
                success = False
                logger.warning(f"Job {job_id} chunk {i + 1}/{len(chunks)} failed: {e}")
        except Exception as e:
            success = False
            logger.warning(f"Job {job_id} chunk {i + 1}/{len(chunks)} failed: {e}")

        await increment_job_progress(job_id, success=success)

        if (i + 1) % 100 == 0:
            logger.info(f"Job {job_id}: {i + 1}/{len(chunks)} uploaded")

    await complete_job(job_id)
    job = await get_job(job_id)
    logger.info(f"Job {job_id} finished: {job}")


#: Suivi d'une indexation confiée à OpenRAG : toutes les quelques secondes, et pas indéfiniment.
SUIVI_DOCUMENT_S = 3.0
SUIVI_DOCUMENT_MAX_S = 1800.0
_ETATS_REUSSIS = ("COMPLETED", "SUCCESS")
_ETATS_ECHOUES = ("FAILED", "CANCELLED")


async def _indexer_document_background(job_id: str, collection: str, filename: str, content: bytes) -> None:
    """Un document entier part vers OpenRAG, qui le lit et le découpe ; on suit sa tâche jusqu'au
    bout pour que le travail dise vrai (réussi, ou en échec avec la raison d'OpenRAG)."""
    import time

    client = OpenRAGClient(timeout=300.0)
    await update_job(job_id, status="uploading")
    erreur = None
    try:
        envoi = await client.upload_document(collection, filename, content, formats.type_mime(filename), metadata={"title": filename})
        tache, debut = envoi.task_id, time.monotonic()
        while tache:
            etat = str((await client.task_state(tache)).task_state or "").upper()
            if etat in _ETATS_REUSSIS:
                break
            if etat in _ETATS_ECHOUES:
                erreur = f"OpenRAG n'a pas pu lire « {filename} » : {await client.task_error(tache) or etat}"
                break
            if time.monotonic() - debut > SUIVI_DOCUMENT_MAX_S:
                erreur = f"OpenRAG n'a pas fini de lire « {filename} » en {int(SUIVI_DOCUMENT_MAX_S // 60)} minutes."
                break
            await asyncio.sleep(SUIVI_DOCUMENT_S)
    except httpx.HTTPStatusError as e:
        # 409 : OpenRAG a déjà ce document (reprise après arrêt) — compté comme réussi.
        if e.response is None or e.response.status_code != 409:
            code = e.response.status_code if e.response is not None else "?"
            erreur = f"OpenRAG a refusé « {filename} » (format ou taille)." if code in (413, 415, 422) else f"OpenRAG a répondu {code} pour « {filename} »."
    except Exception as e:  # noqa: BLE001
        erreur = f"Envoi de « {filename} » à OpenRAG impossible : {type(e).__name__}"
    if erreur:
        logger.warning("Job %s : %s", job_id, erreur)
        await update_job(job_id, error=erreur)
    await increment_job_progress(job_id, success=erreur is None)
    await complete_job(job_id)


ETATS_EN_COURS = ("chunking", "chunking_done", "pending", "uploading")


async def reprendre_les_travaux_interrompus() -> list[str]:
    """Au démarrage : les indexations qu'un arrêt du backend a coupées reprennent depuis le
    fichier source conservé (redéposer le même morceau est sans effet : OpenRAG répond 409, compté
    comme réussi). Sans fichier source, le travail est marqué « interrupted » et dit quoi faire.
    Avant : la tâche de fond disparaissait avec le processus, le travail restait « uploading »."""
    from app.database import async_session
    from app.models.db import IngestJob, SourceFile

    async with async_session() as session:
        travaux = (await session.execute(select(IngestJob).where(IngestJob.status.in_(ETATS_EN_COURS)))).scalars().all()
        travaux = [(t.job_id, t.collection_name, t.filename, t.strategy, t.sensitivity) for t in travaux]

    repris = []
    for job_id, collection, filename, strategy, sensitivity in travaux:
        async with async_session() as session:
            sf = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection, SourceFile.filename == filename))).scalars().first()
            chemin = Path(sf.storage_path) if sf and sf.storage_path else None
        if not chemin or not chemin.exists():
            await update_job(job_id, status="interrupted", error="Indexation interrompue par un redémarrage du service, et le fichier n'est plus conservé : redéposez-le.")
            continue
        if strategy == STRATEGIE_DOCUMENT:
            await update_job(job_id, status="uploading", total_chunks=1, uploaded_chunks=0, failed_chunks=0, error="Repris après un redémarrage du service.")
            await _indexer_document_background(job_id, collection, filename, chemin.read_bytes())
            repris.append(job_id)
            continue
        try:
            texte = texte_ou_refus(chemin.read_bytes(), filename)
            strategie_valide = valider_strategy(strategy or "auto")
            sensibilite_valide = valider_sensibilite(sensitivity or "public")
            if strategie_valide is None or sensibilite_valide is None:
                raise ValueError(f"stratégie « {strategy} » ou sensibilité « {sensitivity} » inconnue")
            morceaux = chunk_document(texte, strategy=strategie_valide, max_chars=512, overlap=50, sensitivity=sensibilite_valide)
        except Exception as e:  # noqa: BLE001
            await update_job(job_id, status="interrupted", error=f"Reprise impossible : {e}")
            continue
        await update_job(job_id, status="uploading", total_chunks=len(morceaux), uploaded_chunks=0, failed_chunks=0, error="Repris après un redémarrage du service.")
        await _upload_chunks_background(job_id, collection, morceaux)
        repris.append(job_id)
    if travaux:
        logger.info("Reprise au démarrage : %d travail(aux) interrompu(s), %d repris", len(travaux), len(repris))
    return repris


MESSAGE_FORMAT = formats.MESSAGE_FORMAT


def texte_ou_refus(content: bytes, filename: str) -> str:
    """Le texte du fichier, ou 415. Le découpage maison ne lit que du texte ; un document (PDF,
    Word…) passe par `_ingest_document`, un binaire inconnu est refusé — il partait autrefois
    décodé « avec remplacement », en caractères illisibles (diagnostic d'octobre 2026)."""
    if formats.nature(filename, content) == "texte":
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("cp1252")  # un .txt enregistré sous Windows
            except UnicodeDecodeError:
                pass
    raise HTTPException(status_code=415, detail=MESSAGE_FORMAT)


async def _exiger_gestion(collection: str, user: CurrentUser) -> None:
    """Déposer des documents, c'est écrire dans la collection : créateur, groupe <nom>-admin ou
    superadmin. Avant : un jeton suffisait pour alimenter la collection d'un autre."""
    from app.routers.publication import _fiche_pour

    await _fiche_pour(collection, user, ecrire=True)


async def _ingest_content(
    collection: str,
    filename: str,
    content: bytes,
    strategy: Strategy,
    sensitivity: Sensitivity,
    source_path: str = "",
) -> dict:
    """Common ingest logic for file upload and URL fetch."""
    nature = formats.nature(filename, content)
    if nature is None:
        raise HTTPException(status_code=415, detail=MESSAGE_FORMAT)
    if nature == "document":
        return await _ingest_document(collection, filename, content, sensitivity, source_path)
    text = texte_ou_refus(content, filename)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Fichier vide")

    chunks = chunk_document(text, strategy=strategy, max_chars=512, overlap=50, sensitivity=sensitivity)
    if not chunks:
        raise HTTPException(status_code=400, detail="Aucun chunk produit")

    # Create partition in OpenRAG (best-effort)
    client = OpenRAGClient()
    try:
        await client.create_partition(collection)
    except Exception:
        pass

    # R7 — Save source file
    saved_path = _save_source_file(collection, filename, content)

    # Record source file in DB
    from app.database import async_session
    from app.models.db import SourceFile

    checksum = hashlib.sha256(content).hexdigest()
    async with async_session() as session:
        # Une ligne par (collection, fichier) : redéposer ou réindexer met la ligne à jour au lieu
        # d'en ajouter une (avant : N lignes, puis 2N, puis 4N à chaque réindexation).
        sf = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection, SourceFile.filename == filename))).scalars().first()
        if sf is None:
            sf = SourceFile(collection_name=collection, filename=filename)
            session.add(sf)
        if source_path.startswith("http") or not sf.original_url:
            sf.original_url = source_path if source_path.startswith("http") else ""
        sf.storage_path = saved_path
        sf.file_size = len(content)
        sf.checksum = checksum
        sf.strategy_used = strategy
        sf.chunks_produced = len(chunks)
        await session.commit()

    # Create job in DB and start background upload
    job = await create_job(
        collection=collection,
        filename=filename,
        strategy=strategy,
        sensitivity=sensitivity,
        source_path=saved_path,
    )
    await update_job(job["job_id"], total_chunks=len(chunks))

    asyncio.create_task(_upload_chunks_background(job["job_id"], collection, chunks))

    return {
        "job_id": job["job_id"],
        "collection": collection,
        "filename": filename,
        "strategy": strategy,
        "sensitivity": sensitivity,
        "total_chunks": len(chunks),
        "status": "chunking_done",
        "track_url": f"/api/ingest/jobs/{job['job_id']}",
    }


#: La « stratégie » d'un document : c'est OpenRAG qui le découpe.
STRATEGIE_DOCUMENT = "openrag"
DOCUMENT_MAX_OCTETS = 50 * 1024 * 1024


async def _enregistrer_source(collection: str, filename: str, content: bytes, strategy: str, chunks: int, source_path: str) -> str:
    """Le fichier source gardé sur le disque (réindexation, reprise) et sa ligne en base."""
    saved_path = _save_source_file(collection, filename, content)
    from app.database import async_session
    from app.models.db import SourceFile

    async with async_session() as session:
        sf = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection, SourceFile.filename == filename))).scalars().first()
        if sf is None:
            sf = SourceFile(collection_name=collection, filename=filename)
            session.add(sf)
        if source_path.startswith("http") or not sf.original_url:
            sf.original_url = source_path if source_path.startswith("http") else ""
        sf.storage_path = saved_path
        sf.file_size = len(content)
        sf.checksum = hashlib.sha256(content).hexdigest()
        sf.strategy_used = strategy
        sf.chunks_produced = chunks
        await session.commit()
    return saved_path


async def _ingest_document(collection: str, filename: str, content: bytes, sensitivity: Sensitivity, source_path: str = "") -> dict:
    """Un document (PDF, Word…) : gardé comme source, puis confié tel quel à OpenRAG."""
    if len(content) > DOCUMENT_MAX_OCTETS:
        raise HTTPException(status_code=413, detail=f"« {filename} » dépasse {DOCUMENT_MAX_OCTETS // 1024 // 1024} Mo.")
    client = OpenRAGClient()
    try:
        await client.create_partition(collection)
    except Exception:
        pass
    saved_path = await _enregistrer_source(collection, filename, content, STRATEGIE_DOCUMENT, 0, source_path)
    job = await create_job(collection=collection, filename=filename, strategy=STRATEGIE_DOCUMENT, sensitivity=sensitivity, source_path=saved_path)
    await update_job(job["job_id"], total_chunks=1)
    asyncio.create_task(_indexer_document_background(job["job_id"], collection, filename, content))
    return {
        "job_id": job["job_id"],
        "collection": collection,
        "filename": filename,
        "strategy": STRATEGIE_DOCUMENT,
        "sensitivity": sensitivity,
        "total_chunks": None,
        "nature": "document",
        "status": "uploading",
        "track_url": f"/api/ingest/jobs/{job['job_id']}",
    }


@router.post("/{collection}")
async def ingest_file(
    collection: str,
    file: UploadFile = File(...),
    strategy: Strategy = Form(Strategy.AUTO),
    sensitivity: Sensitivity = Form(Sensitivity.PUBLIC),
    max_chars: int = Form(512),
    overlap: int = Form(50),
    user: CurrentUser = Depends(current_user),
):
    """Upload a file, chunk it intelligently, and index in OpenRAG."""
    await _exiger_gestion(collection, user)
    content = await file.read()
    return await _ingest_content(
        collection=collection,
        filename=file.filename or "unknown",
        content=content,
        strategy=strategy,
        sensitivity=sensitivity,
    )


class IngestFromUrlRequest(BaseModel):
    url: str
    strategy: Strategy = Strategy.AUTO
    sensitivity: Sensitivity = Sensitivity.PUBLIC


@router.post("/{collection}/from-url")
async def ingest_from_url(collection: str, req: IngestFromUrlRequest, user: CurrentUser = Depends(current_user)):
    """Download a remote file by URL, chunk it, and index in OpenRAG."""
    await _exiger_gestion(collection, user)
    assert_public_http_url(req.url)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
            event_hooks={"request": [ssrf_request_guard]},
        ) as client:
            resp = await client.get(req.url)
            if resp.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"HTTP {resp.status_code}")
            content = resp.content
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Timeout")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = req.url.rstrip("/").split("/")[-1] or "remote-file"

    return await _ingest_content(
        collection=collection,
        filename=filename,
        content=content,
        strategy=req.strategy,
        sensitivity=req.sensitivity,
        source_path=req.url,
    )


@router.post("/{collection}/reindex")
async def reindex_collection(collection: str, strategy: Strategy = Strategy.AUTO, sensitivity: Sensitivity = Sensitivity.PUBLIC, user: CurrentUser = Depends(current_user)):
    """Re-index all source files of a collection with a new strategy.

    Uses source files saved by R7 to re-chunk and re-index without re-upload.
    """
    await _exiger_gestion(collection, user)
    from app.database import async_session as db_session
    from app.models.db import SourceFile

    # Get all source files for this collection
    async with db_session() as session:
        result = await session.execute(select(SourceFile).where(SourceFile.collection_name == collection))
        source_files = result.scalars().all()

    if not source_files:
        raise HTTPException(status_code=400, detail="Aucun fichier source enregistre pour cette collection. Re-uploadez vos documents.")

    # Tout vérifier AVANT d'effacer : chaque source est présente, lisible et produit des
    # morceaux avec la nouvelle stratégie. Sinon on refuse, et la collection reste intacte.
    uniques: dict[str, SourceFile] = {}
    for sf in source_files:
        uniques.setdefault(sf.filename, sf)  # d'anciennes lignes en double : une seule par fichier
    contenus = []
    for sf in uniques.values():
        path = Path(sf.storage_path)
        if not path.exists():
            raise HTTPException(status_code=409, detail=f"Le fichier source « {sf.filename} » n'est plus conservé : redéposez-le avant de réindexer.")
        content = path.read_bytes()
        if formats.nature(sf.filename, content) == "document":
            contenus.append((sf, content))
            continue
        if not chunk_document(texte_ou_refus(content, sf.filename), strategy=strategy, max_chars=512, overlap=50, sensitivity=sensitivity):
            raise HTTPException(status_code=422, detail=f"Avec ce découpage, « {sf.filename} » ne produirait aucun passage : choisissez un autre découpage.")
        contenus.append((sf, content))

    # Vider la partition puis la recréer : avant, les anciens morceaux restaient à côté des
    # nouveaux, et chaque réindexation doublait le corpus dans OpenRAG.
    client = OpenRAGClient()
    await client.delete_partition(collection)
    await client.create_partition(collection)

    total_jobs = []
    for sf, content in contenus:
        result = await _ingest_content(
            collection=collection,
            filename=sf.filename,
            content=content,
            strategy=strategy,
            sensitivity=sensitivity,
            source_path=sf.storage_path,
        )
        total_jobs.append(result)

    return {
        "status": "reindexing",
        "collection": collection,
        "strategy": strategy,
        "files_reindexed": len(total_jobs),
        "jobs": [j["job_id"] for j in total_jobs],
    }


@router.get("/{collection}/sources")
async def list_source_files(collection: str, user: CurrentUser = Depends(current_user)):
    """List all stored source files for a collection."""
    from app.routers._droits import lire_la_collection

    await lire_la_collection(collection, user)
    from app.database import async_session as db_session
    from app.models.db import SourceFile

    async with db_session() as session:
        result = await session.execute(select(SourceFile).where(SourceFile.collection_name == collection).order_by(SourceFile.created_at.desc()))
        files = result.scalars().all()
        return {"sources": [f.to_dict() for f in files]}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user: CurrentUser = Depends(current_user)):
    from app.routers._droits import peut_lire_nom

    job = await get_job(job_id)
    if not job or not await peut_lire_nom(job.get("collection", ""), user):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs")
async def list_all_jobs(collection: str | None = Query(None), user: CurrentUser = Depends(current_user)):
    """Les travaux des seules collections que l'appelant peut lire (avant : tous)."""
    from app.routers._droits import peut_lire_nom

    travaux = await list_jobs(collection=collection)
    lisibles: dict[str, bool] = {}
    for t in travaux:
        c = t.get("collection", "")
        if c not in lisibles:
            lisibles[c] = await peut_lire_nom(c, user)
    return {"jobs": [t for t in travaux if lisibles[t.get("collection", "")]]}
