"""Ingest router — envoi des fichiers entiers à OpenRAG, qui les découpe (ADR-0005)."""

import asyncio
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import CurrentUser, current_user
from app.config import settings
from app.security_utils import assert_public_http_url, ensure_within, safe_filename, ssrf_request_guard
from app.services import formats
from app.services.chunker import Sensitivity, valider_sensibilite
from app.services.job_store import complete_job, create_job, get_job, increment_job_progress, list_jobs, update_job
from app.services.openrag_client import EnvoiDocument, OpenRAGClient

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])
logger = logging.getLogger("myrag.ingest")

# R7 — Source file storage directory
SOURCES_DIR = Path(settings.data_dir) / "_sources"

MESSAGE_FORMAT = formats.MESSAGE_FORMAT


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


#: Suivi d'une indexation confiée à OpenRAG : toutes les quelques secondes, et pas indéfiniment.
SUIVI_DOCUMENT_S = 3.0
SUIVI_DOCUMENT_MAX_S = 1800.0
_ETATS_REUSSIS = ("COMPLETED", "SUCCESS")
_ETATS_ECHOUES = ("FAILED", "CANCELLED")


async def attendre_indexation(client: OpenRAGClient, envoi: EnvoiDocument, filename: str) -> str | None:
    """Suit la tâche d'indexation d'un document confié à OpenRAG, jusqu'à sa fin : rend
    None s'il est indexé, la raison sinon (échec dit par OpenRAG, ou lecture trop longue).
    Sans tâche rendue, c'est réussi : OpenRAG a fait le travail de suite. Partagé par le
    dépôt (travaux) et les amorces (imports rejouables)."""
    import time

    tache, debut = envoi.task_id, time.monotonic()
    while tache:
        etat = str((await client.task_state(tache)).task_state or "").upper()
        if etat in _ETATS_REUSSIS:
            return None
        if etat in _ETATS_ECHOUES:
            return f"OpenRAG n'a pas pu lire « {filename} » : {await client.task_error(tache) or etat}"
        if time.monotonic() - debut > SUIVI_DOCUMENT_MAX_S:
            return f"OpenRAG n'a pas fini de lire « {filename} » en {int(SUIVI_DOCUMENT_MAX_S // 60)} minutes."
        await asyncio.sleep(SUIVI_DOCUMENT_S)
    return None


async def _indexer_document_background(job_id: str, collection: str, filename: str, content: bytes, sensitivity: str) -> None:
    """Le fichier part entier vers OpenRAG, qui le lit et le découpe ; on suit sa tâche jusqu'au
    bout pour que le travail dise vrai (réussi, ou en échec avec la raison d'OpenRAG). La
    sensibilité voyage en métadonnée — elle n'était jamais transmise du temps des morceaux."""
    client = OpenRAGClient(timeout=300.0)
    await update_job(job_id, status="uploading")
    erreur = None
    try:
        envoi = await client.upload_document(collection, filename, content, formats.type_mime(filename), metadata={"title": filename, "sensitivity": sensitivity})
        erreur = await attendre_indexation(client, envoi, filename)
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
    fichier source conservé, renvoyé entier (redéposer le même document est sans effet :
    OpenRAG répond 409, compté comme réussi). Sans fichier source, le travail est marqué
    « interrupted » et dit quoi faire. Les travaux antérieurs à la délégation du découpage
    (ADR-0005) basculent ici dans le nouveau régime : leur source part entière."""
    from app.database import async_session
    from app.models.db import IngestJob, SourceFile

    async with async_session() as session:
        travaux = (await session.execute(select(IngestJob).where(IngestJob.status.in_(ETATS_EN_COURS)))).scalars().all()
        travaux = [(t.job_id, t.collection_name, t.filename, t.sensitivity) for t in travaux]

    repris = []
    for job_id, collection, filename, sensitivity in travaux:
        async with async_session() as session:
            sf = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection, SourceFile.filename == filename))).scalars().first()
            chemin = Path(sf.storage_path) if sf and sf.storage_path else None
        if not chemin or not chemin.exists():
            await update_job(job_id, status="interrupted", error="Indexation interrompue par un redémarrage du service, et le fichier n'est plus conservé : redéposez-le.")
            continue
        await update_job(job_id, status="uploading", total_chunks=1, uploaded_chunks=0, failed_chunks=0, error="Repris après un redémarrage du service.")
        try:
            contenu = chemin.read_bytes()
        except OSError as e:
            # Un fichier illisible ne doit pas arrêter toute la reprise : ce travail dit
            # quoi faire, les suivants reprennent.
            await update_job(
                job_id,
                status="interrupted",
                error=f"Indexation interrompue par un redémarrage du service, et le fichier conservé ne se lit plus ({type(e).__name__}) : redéposez-le.",
            )
            continue
        await _indexer_document_background(job_id, collection, filename, contenu, sensitivity or Sensitivity.PUBLIC)
        repris.append(job_id)
    if travaux:
        logger.info("Reprise au démarrage : %d travail(aux) interrompu(s), %d repris", len(travaux), len(repris))
    return repris


async def _exiger_gestion(collection: str, user: CurrentUser) -> None:
    """Déposer des documents, c'est écrire dans la collection : créateur, groupe <nom>-admin ou
    superadmin. Avant : un jeton suffisait pour alimenter la collection d'un autre."""
    from app.routers.publication import _fiche_pour

    await _fiche_pour(collection, user, ecrire=True)


class DepotResultat(BaseModel):
    """Réponse d'un dépôt accepté : le travail créé et où le suivre.

    Le découpage est celui d'OpenRAG (ADR-0005) : « total_chunks » vaut None —
    OpenRAG ne compte les passages qu'en les lisant."""

    job_id: str
    collection: str
    filename: str
    strategy: str
    sensitivity: str
    total_chunks: int | None = None
    status: str
    track_url: str


#: La « stratégie » d'un dépôt : c'est OpenRAG qui découpe (ADR-0005).
STRATEGIE_DOCUMENT = "openrag"
DOCUMENT_MAX_OCTETS = 50 * 1024 * 1024


async def _enregistrer_source(collection: str, filename: str, content: bytes, chunks: int, source_path: str, sensitivity: str) -> str:
    """Le fichier source gardé sur le disque (réindexation, reprise) et sa ligne en base —
    avec sa sensibilité, reprise telle quelle à la réindexation."""
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
        sf.strategy_used = STRATEGIE_DOCUMENT
        sf.chunks_produced = chunks
        sf.sensitivity = sensitivity
        await session.commit()
    return saved_path


async def _ingest_document(collection: str, filename: str, content: bytes, sensitivity: Sensitivity, source_path: str = "") -> DepotResultat:
    """Tout fichier (texte compris) : gardé comme source, puis confié entier à OpenRAG,
    qui le découpe (ADR-0005)."""
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if formats.nature(filename, content) is not formats.Nature.DOCUMENT:
        raise HTTPException(status_code=415, detail=MESSAGE_FORMAT)
    if len(content) > DOCUMENT_MAX_OCTETS:
        raise HTTPException(status_code=413, detail=f"« {filename} » dépasse {DOCUMENT_MAX_OCTETS // 1024 // 1024} Mo.")
    client = OpenRAGClient()
    try:
        await client.create_partition(collection)
    except Exception:
        pass
    saved_path = await _enregistrer_source(collection, filename, content, 0, source_path, sensitivity)
    job = await create_job(collection=collection, filename=filename, strategy=STRATEGIE_DOCUMENT, sensitivity=sensitivity, source_path=saved_path)
    await update_job(job["job_id"], total_chunks=1)
    asyncio.create_task(_indexer_document_background(job["job_id"], collection, filename, content, sensitivity))
    return DepotResultat(
        job_id=job["job_id"],
        collection=collection,
        filename=filename,
        strategy=STRATEGIE_DOCUMENT,
        sensitivity=sensitivity,
        total_chunks=None,
        status="uploading",
        track_url=f"/api/ingest/jobs/{job['job_id']}",
    )


@router.post("/{collection}")
async def ingest_file(
    collection: str,
    file: UploadFile = File(...),
    sensitivity: Sensitivity = Form(Sensitivity.PUBLIC),
    user: CurrentUser = Depends(current_user),
) -> DepotResultat:
    """Upload a file and hand it to OpenRAG, which chunks it (ADR-0005)."""
    await _exiger_gestion(collection, user)
    content = await file.read()
    return await _ingest_document(
        collection=collection,
        filename=file.filename or "unknown",
        content=content,
        sensitivity=sensitivity,
    )


class IngestFromUrlRequest(BaseModel):
    url: str
    sensitivity: Sensitivity = Sensitivity.PUBLIC


@router.post("/{collection}/from-url")
async def ingest_from_url(collection: str, req: IngestFromUrlRequest, user: CurrentUser = Depends(current_user)) -> DepotResultat:
    """Download a remote file by URL and hand it to OpenRAG, which chunks it (ADR-0005)."""
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

    # Le nom se déduit du chemin de l'URL, sans la requête ni le fragment : « note.md?download=1 »
    # ne serait pas un .md, et le dépôt refuserait (415) des textes acceptés avant.
    filename = urlsplit(req.url).path.rstrip("/").split("/")[-1] or "remote-file"

    return await _ingest_document(
        collection=collection,
        filename=filename,
        content=content,
        sensitivity=req.sensitivity,
        source_path=req.url,
    )


@router.post("/{collection}/reindex")
async def reindex_collection(collection: str, user: CurrentUser = Depends(current_user)):
    """Réindexer une collection : vider sa partition OpenRAG et renvoyer chaque fichier
    source tel quel. Action de maintenance (partition perdue, conversion d'une collection
    indexée avant la délégation du découpage — ADR-0005) ; le découpage est toujours celui
    d'OpenRAG, la sensibilité celle enregistrée par fichier au dépôt."""
    await _exiger_gestion(collection, user)
    from app.database import async_session as db_session
    from app.models.db import SourceFile

    # Get all source files for this collection
    async with db_session() as session:
        result = await session.execute(select(SourceFile).where(SourceFile.collection_name == collection))
        source_files = result.scalars().all()

    if not source_files:
        raise HTTPException(status_code=400, detail="Aucun fichier source enregistre pour cette collection. Re-uploadez vos documents.")

    # Tout vérifier AVANT d'effacer : chaque source est présente, lisible et acceptable par
    # OpenRAG — format et taille, que l'envoi ne dirait qu'après coup. Sinon on refuse, et
    # la collection reste intacte.
    uniques: dict[str, SourceFile] = {}
    for sf in source_files:
        uniques.setdefault(sf.filename, sf)  # d'anciennes lignes en double : une seule par fichier
    contenus = []
    for sf in uniques.values():
        path = Path(sf.storage_path)
        if not path.exists():
            raise HTTPException(status_code=409, detail=f"Le fichier source « {sf.filename} » n'est plus conservé : redéposez-le avant de réindexer.")
        content = path.read_bytes()
        if not content:
            raise HTTPException(status_code=400, detail=f"Le fichier source « {sf.filename} » est vide : redéposez-le avant de réindexer.")
        if len(content) > DOCUMENT_MAX_OCTETS:
            raise HTTPException(
                status_code=413, detail=f"Le fichier source « {sf.filename} » dépasse {DOCUMENT_MAX_OCTETS // 1024 // 1024} Mo : redéposez-le en plus petit avant de réindexer."
            )
        if formats.nature(sf.filename, content) is not formats.Nature.DOCUMENT:
            raise HTTPException(
                status_code=415,
                detail=f"Le fichier source « {sf.filename} » n'est plus accepté (CSV, par exemple) : retirez cette source de la collection, puis redéposez le fichier converti en .txt ou .md avant de réindexer.",
            )
        contenus.append((sf, content))

    # Vider la partition puis la recréer : avant, les anciens morceaux restaient à côté des
    # nouveaux, et chaque réindexation doublait le corpus dans OpenRAG.
    client = OpenRAGClient()
    await client.delete_partition(collection)
    await client.create_partition(collection)

    total_jobs = []
    for sf, content in contenus:
        result = await _ingest_document(
            collection=collection,
            filename=sf.filename,
            content=content,
            sensitivity=valider_sensibilite(sf.sensitivity or "public") or Sensitivity.PUBLIC,
            source_path=sf.storage_path,
        )
        total_jobs.append(result)

    return {
        "status": "reindexing",
        "collection": collection,
        "files_reindexed": len(total_jobs),
        "jobs": [j.job_id for j in total_jobs],
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


@router.delete("/{collection}/sources/{source_id}")
async def delete_source_file(collection: str, source_id: int, user: CurrentUser = Depends(current_user)):
    """Retirer un fichier source de la collection : sa ligne disparaît, et le fichier
    conservé avec elle — sauf si une autre ligne le désigne encore (les doublons
    d'avant l'ADR-0005 partagent le même fichier ; la réindexation n'en garde qu'une).
    Ses passages restent dans OpenRAG jusqu'à la prochaine réindexation (elle vide la
    partition) — OpenRAG ne sait pas retirer les morceaux d'un document —, sauf si
    c'est la dernière source : la partition est vidée d'abord, sinon ses passages
    seraient indépurables (la réindexation refuse une collection sans sources). C'est
    la sortie de secours d'une source devenue inacceptable au dépôt (CSV,
    .markdown — ADR-0005) : sans elle, la réindexation la refuserait pour toujours."""
    await _exiger_gestion(collection, user)
    from sqlalchemy import func

    from app.database import async_session as db_session
    from app.models.db import SourceFile

    async with db_session() as session:
        sf = (await session.execute(select(SourceFile).where(SourceFile.id == source_id, SourceFile.collection_name == collection))).scalars().first()
        if sf is None:
            raise HTTPException(status_code=404, detail="Fichier source inconnu dans cette collection.")
        nom, chemin = sf.filename, sf.storage_path
        partage = (await session.execute(select(func.count()).select_from(SourceFile).where(SourceFile.storage_path == chemin, SourceFile.id != sf.id))).scalar_one()
        restantes = (await session.execute(select(func.count()).select_from(SourceFile).where(SourceFile.collection_name == collection, SourceFile.id != sf.id))).scalar_one()
        if restantes == 0:
            # Dernière source : vider la partition AVANT d'oublier la ligne — dans
            # l'autre sens, les passages resteraient sans aucune voie de nettoyage.
            # OpenRAG injoignable en plein retrait : la ligne et le fichier restent
            # (le retrait se rejoue) ; la partition, elle, ne peut qu'être vidée —
            # c'est le but — et se recrée au retrait repris comme au dépôt.
            client = OpenRAGClient(timeout=120.0)
            try:
                await client.delete_partition(collection)
                await client.create_partition(collection)
            except httpx.HTTPError as e:
                logger.warning("Retrait de la dernière source de « %s » : OpenRAG injoignable (%s)", collection, type(e).__name__)
                raise HTTPException(
                    status_code=503,
                    detail="OpenRAG n'est pas accessible : la source n'a pas été retirée, réessayez.",
                )
        await session.delete(sf)
        await session.commit()
    if partage == 0:
        try:
            Path(chemin).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Source « %s » : le fichier conservé %s n'a pas pu être effacé du disque (%s)", nom, chemin, e)
    return {"status": "deleted", "collection": collection, "filename": nom}


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
