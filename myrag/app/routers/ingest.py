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
from app.services import conversion, formats
from app.services.chunker import Sensitivity, Strategy, chunk_document, valider_sensibilite, valider_strategy
from app.services.indexeur import DejaPresent, Indexeur, IndexeurOpenRAG, Refuse, qualite_echec
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


#: Suivi d'une indexation confiée à OpenRAG : au plus toutes les quelques secondes, et pas
#: indéfiniment. Les premières vérifications sont plus rapprochées (`pause_de_suivi`).
SUIVI_DOCUMENT_S = 3.0
SUIVI_DOCUMENT_MAX_S = 1800.0


#: La langue transmise à l'indexeur quand la source n'en dit rien : il y rédige le contexte de chaque
#: passage (sans elle, OpenRAG l'écrit en anglais). Une détection par document viendra avec #157.
LANGUE_PAR_DEFAUT = "fr"
#: Ce qu'on dit d'un scan que l'indexeur n'a pas pu lire (#145).
CONSEIL_SCAN = (
    "C'est un scan, sans texte lisible : il ne sera trouvé qu'une fois la reconnaissance de caractères en place. "
    "Si vous avez sa version électronique (Word, LibreOffice, PDF exporté), de préférence non signée, déposez-la plutôt."
)


def pause_de_suivi(ecoule: float) -> float:
    """L'attente avant de redemander où en est la lecture d'un document. La plupart des documents
    sont lus en quelques secondes (9 s en médiane sur un import réel) : vérifier toutes les 3 s
    laissait chaque envoi inoccupé 1 à 2 s en moyenne après sa fin. On vérifie chaque seconde au
    début, puis on espace pour les longs documents, sans dépasser SUIVI_DOCUMENT_S."""
    if SUIVI_DOCUMENT_S <= 0:
        return SUIVI_DOCUMENT_S
    if ecoule < 15:
        return min(1.0, SUIVI_DOCUMENT_S)
    if ecoule < 60:
        return min(2.0, SUIVI_DOCUMENT_S)
    return SUIVI_DOCUMENT_S


_ETATS_REUSSIS = ("COMPLETED", "SUCCESS")
_ETATS_ECHOUES = ("FAILED", "CANCELLED")


def _indexeur(timeout: float = 300.0) -> Indexeur:
    """Le moteur qui reçoit les documents (app.services.indexeur) : OpenRAG aujourd'hui. Seul point
    où il se construit, pour les documents déposés comme pour Résana."""
    return IndexeurOpenRAG(OpenRAGClient(timeout=timeout))


async def _indexer_document_background(
    job_id: str, collection: str, filename: str, content: bytes, metadata: dict | None = None, file_id: str | None = None
) -> tuple[str | None, str | None, dict | None]:
    """Un document entier part vers l'indexeur, qui le lit et le découpe ; on suit sa lecture
    jusqu'au bout pour que le travail dise vrai (réussi, ou en échec avec la raison). Rend
    (identifiant du document chez l'indexeur s'il l'a reçu, erreur ou None, qualité de
    l'indexation ou None — `indexeur.qualite_lecture`) : l'import Résana
    garde l'identifiant pour remplacer ou retirer ce document plus tard, même si sa lecture a
    échoué ou traîne. `metadata` complète le titre ; `file_id` fixe l'identifiant (`DejaPresent`
    dit alors que ce document-là est déjà indexé, compté comme réussi)."""
    import time

    indexeur = _indexeur()
    await update_job(job_id, status="uploading")
    erreur = None
    identifiant = None
    qualite: dict | None = None
    # Un scan (PDF sans texte) part quand même : l'indexeur le lira s'il a l'OCR (#145).
    scan = bool((metadata or {}).get("scan")) or await asyncio.to_thread(formats.est_un_scan, filename, content)
    try:
        envoi = await indexeur.envoyer(
            collection,
            filename,
            content,
            mime=formats.type_mime(filename),
            metadata={"title": filename, "language": LANGUE_PAR_DEFAUT, **(metadata or {}), **({"scan": True} if scan else {})},
            identifiant=file_id,
        )
        identifiant, tache, debut = envoi.identifiant, envoi.tache, time.monotonic()
        while tache:
            suivi = await indexeur.suivre(tache)
            if suivi.lecture == "lu":
                qualite = suivi.qualite
                break
            if suivi.lecture == "echec":
                erreur = f"OpenRAG n'a pas pu lire « {filename} » : {suivi.raison}"
                qualite = qualite_echec(suivi.raison)
                break
            if time.monotonic() - debut > SUIVI_DOCUMENT_MAX_S:
                erreur = f"OpenRAG n'a pas fini de lire « {filename} » en {int(SUIVI_DOCUMENT_MAX_S // 60)} minutes."
                break
            await asyncio.sleep(pause_de_suivi(time.monotonic() - debut))
    except DejaPresent:
        # Déjà indexé (reprise après arrêt) — compté comme réussi.
        identifiant = file_id
    except Refuse as e:
        erreur = f"OpenRAG a refusé « {filename} » (format ou taille)." if e.statut in (413, 415, 422) else f"OpenRAG a répondu {e.statut or '?'} pour « {filename} »."
        qualite = {"etat": "echec"}
    except Exception as e:  # noqa: BLE001
        erreur = f"Envoi de « {filename} » à OpenRAG impossible : {type(e).__name__}"
    if erreur and scan and (qualite or {}).get("etat") == "sans_texte":
        erreur = f"{erreur} {CONSEIL_SCAN}"
    if erreur:
        logger.warning("Job %s : %s", job_id, erreur)
        await update_job(job_id, error=erreur)
    elif avis := avis_qualite(filename, qualite):
        # Lu, mais pas entièrement : le travail réussit, et dit ce qui manque.
        await update_job(job_id, error=avis)
    await increment_job_progress(job_id, success=erreur is None)
    await complete_job(job_id)
    return identifiant, erreur, qualite


def avis_qualite(filename: str, qualite: dict | None) -> str | None:
    """La phrase qui dit ce qui manque à un document lu, ou None s'il est complet (ou si l'indexeur
    ne le dit pas). Ce qu'un tableur a perdu (lignes au-delà de la borne, formules sans valeur,
    feuilles masquées) est dit quel que soit l'état : un tableur tronqué dont deux passages ont aussi
    perdu leur contexte est « sans contexte », mais sa troncature compte davantage."""
    qualite = qualite or {}
    etat = qualite.get("etat")
    manques: list[str] = []
    tableur = qualite.get("tableur") or {}
    if tableur.get("tronque"):
        gardees, total = tableur.get("lignes_gardees"), tableur.get("lignes_total")
        part = f"{gardees} lignes sur {total}" if isinstance(gardees, int) and isinstance(total, int) else "une partie de ses lignes"
        manques.append(f"seules {part} sont indexées (le tableur dépasse la taille admise) : découpez-le en plusieurs fichiers")
    if etat == "sans_contexte":
        n, total = qualite.get("sans_contexte"), qualite.get("passages")
        if isinstance(n, int) and isinstance(total, int):
            manque = f"{n} de ses {total} passages n'a pas son contexte" if n == 1 else f"{n} de ses {total} passages n'ont pas leur contexte"
        else:
            manque = "une part de ses passages n'a pas son contexte"
        manques.append(f"{manque} : ils se retrouveront moins bien. Ré-indexez-le plus tard")
    elif etat == "degrade":
        manques.append(f"une étape a échoué ({', '.join(qualite.get('etapes') or [])})")
    if tableur.get("formules_sans_valeur"):
        n = tableur["formules_sans_valeur"]
        manques.append(
            f"{n} cellule{'s' if n > 1 else ''} à formule {'sont' if n > 1 else 'est'} vide{'s' if n > 1 else ''} faute de valeur calculée : ouvrez-le et enregistrez-le de nouveau dans Excel ou LibreOffice"
        )
    if tableur.get("feuilles_masquees_ignorees"):
        n = tableur["feuilles_masquees_ignorees"]
        manques.append(f"{n} feuille{'s' if n > 1 else ''} masquée{'s' if n > 1 else ''} n'{'ont' if n > 1 else 'a'} pas été indexée{'s' if n > 1 else ''}")
    if manques:
        return f"« {filename} » est indexé, mais " + " ; ".join(manques) + "."
    return None


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
    if formats.nature(filename, content) is formats.Nature.TEXTE:
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


class DepotResultat(BaseModel):
    """Réponse d'un dépôt accepté : le travail créé et où le suivre.

    « nature » vaut « document » quand le fichier part entier et qu'OpenRAG le découpe
    lui-même ; « total_chunks » vaut alors None — OpenRAG ne compte les passages qu'en
    les lisant."""

    job_id: str
    collection: str
    filename: str
    strategy: str
    sensitivity: str
    total_chunks: int | None = None
    status: str
    track_url: str
    nature: str | None = None


async def _ingest_content(
    collection: str,
    filename: str,
    content: bytes,
    strategy: Strategy,
    sensitivity: Sensitivity,
    source_path: str = "",
) -> DepotResultat:
    """Common ingest logic for file upload and URL fetch."""
    nature = formats.nature(filename, content)
    if nature is None and conversion.active() and conversion.convertible(filename):
        # Un format bureautique que l'indexeur ne lit pas part converti en PDF (#146).
        try:
            content = await conversion.en_pdf(filename, content)
        except conversion.ConversionImpossible as e:
            raise HTTPException(status_code=422, detail=f"« {filename} » n'a pas pu être converti en PDF ({e}). Déposez-le en PDF.") from None
        filename = conversion.nom_pdf(filename)
        nature = formats.nature(filename, content)
    if nature is None:
        raise HTTPException(status_code=415, detail=MESSAGE_FORMAT)
    if nature is formats.Nature.DOCUMENT:
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

    return DepotResultat(
        job_id=job["job_id"],
        collection=collection,
        filename=filename,
        strategy=strategy,
        sensitivity=sensitivity,
        total_chunks=len(chunks),
        status="chunking_done",
        track_url=f"/api/ingest/jobs/{job['job_id']}",
    )


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


async def _ingest_document(collection: str, filename: str, content: bytes, sensitivity: Sensitivity, source_path: str = "") -> DepotResultat:
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
    return DepotResultat(
        job_id=job["job_id"],
        collection=collection,
        filename=filename,
        strategy=STRATEGIE_DOCUMENT,
        sensitivity=sensitivity,
        total_chunks=None,
        status="uploading",
        track_url=f"/api/ingest/jobs/{job['job_id']}",
        nature="document",
    )


@router.post("/{collection}")
async def ingest_file(
    collection: str,
    file: UploadFile = File(...),
    strategy: Strategy = Form(Strategy.AUTO),
    sensitivity: Sensitivity = Form(Sensitivity.PUBLIC),
    max_chars: int = Form(512),
    overlap: int = Form(50),
    user: CurrentUser = Depends(current_user),
) -> DepotResultat:
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
async def ingest_from_url(collection: str, req: IngestFromUrlRequest, user: CurrentUser = Depends(current_user)) -> DepotResultat:
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

    resultat = await _ingest_content(
        collection=collection,
        filename=filename,
        content=content,
        strategy=req.strategy,
        sensitivity=req.sensitivity,
        source_path=req.url,
    )
    await _proposer_le_site(collection, req.url)
    return resultat


async def _proposer_le_site(collection: str, url: str) -> None:
    """Le site d'un document déposé par adresse devient un site déclaré pour MirAI Assistant pour
    navigateur, et la source de la collection si elle n'en a pas encore."""
    from app.services import sources_url
    from app.services.collection_store import get_collection, update_collection

    motif = sources_url.motif_de(url)
    if not motif:
        return
    try:
        await sources_url.ajouter_sites(collection, [motif])
        fiche = await get_collection(collection)
        if fiche is not None and not (fiche.get("source_url") or "").strip():
            await update_collection(collection, {"source_url": motif.removesuffix("*")})
    except Exception as e:  # noqa: BLE001 — une proposition de site ne doit pas faire échouer le dépôt
        logger.warning("%s : site non proposé (%s)", collection, type(e).__name__)


@router.post("/{collection}/reindex")
async def reindex_collection(collection: str, strategy: Strategy = Strategy.AUTO, sensitivity: Sensitivity = Sensitivity.PUBLIC, user: CurrentUser = Depends(current_user)):
    """Re-index all source files of a collection with a new strategy.

    Uses source files saved by R7 to re-chunk and re-index without re-upload.
    """
    await _exiger_gestion(collection, user)
    from app.database import async_session as db_session
    from app.models.db import SourceFile

    # Une collection importée (Résana, Fichiers) ne garde pas de copie de ses documents
    # (docs/resana.md) : on la réindexe en relisant sa source, par sa page (« Tout revérifier »).
    from app.services import sources_importees
    from app.services.collection_store import get_collection

    importee = sources_importees.source_importee(await get_collection(collection))
    if importee:
        nom_source = sources_importees.nom(importee)
        raise HTTPException(status_code=409, detail=f"Une collection {nom_source} se réindexe depuis {nom_source} : « Tout revérifier » sur sa page.")

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
        if formats.nature(sf.filename, content) is formats.Nature.DOCUMENT:
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
