"""Sources router — Legifrance + Drive source management + URL checking."""

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.services.legifrance_client import LegifranceClient, parse_legifrance_url

logger = logging.getLogger("myrag.sources")

router = APIRouter(prefix="/api/sources", tags=["Sources"])


class AddSourceByUrlRequest(BaseModel):
    url: str
    collection: str
    refresh_mode: str = "manual"  # manual | daily | weekly


class AddSourceByIdRequest(BaseModel):
    type: str  # code | article | loi | jo
    legifrance_id: str
    collection: str
    scope: str = ""  # optional: partie_legislative, partie_reglementaire
    refresh_mode: str = "manual"


class SearchLegifranceRequest(BaseModel):
    query: str
    fond: str = "CODE_DATE"
    page_size: int = 10


@router.get("/check-url")
async def check_url(url: str = Query(..., description="URL to check")):
    """Check if a remote URL is accessible and return content info.

    Server-side HEAD request avoids browser CORS restrictions.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.head(url)
            if resp.status_code < 400:
                content_type = resp.headers.get("content-type", "inconnu").split(";")[0].strip()
                content_length = resp.headers.get("content-length")
                return {
                    "accessible": True,
                    "status_code": resp.status_code,
                    "content_type": content_type,
                    "content_length": int(content_length) if content_length else None,
                    "url": str(resp.url),  # final URL after redirects
                }
            return {
                "accessible": False,
                "status_code": resp.status_code,
                "content_type": None,
                "content_length": None,
            }
    except httpx.TimeoutException:
        return {"accessible": False, "error": "timeout"}
    except Exception as e:
        return {"accessible": False, "error": str(e)}


@router.get("/preview-url")
async def preview_url(
    url: str = Query(..., description="URL to preview"),
    max_chars: int = Query(4000, description="Max characters to return"),
):
    """Fetch the first bytes of a remote URL and return as text preview.

    Server-side fetch avoids CORS and X-Frame-Options restrictions.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    return {"content": None, "error": f"HTTP {resp.status_code}"}
                # Read only what we need
                chunks = []
                total = 0
                async for chunk in resp.aiter_text():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_chars:
                        break
                content = "".join(chunks)
                truncated = len(content) >= max_chars
                if truncated:
                    content = content[:max_chars]
                return {"content": content, "truncated": truncated}
    except httpx.TimeoutException:
        return {"content": None, "error": "timeout"}
    except Exception as e:
        return {"content": None, "error": str(e)}


@router.post("/legifrance/parse-url")
async def parse_url(req: AddSourceByUrlRequest):
    """Parse a Legifrance URL and extract the document type and ID."""
    result = parse_legifrance_url(req.url)
    if not result:
        raise HTTPException(status_code=400, detail="URL not recognized as a Legifrance URL")
    return {
        **result,
        "collection": req.collection,
        "refresh_mode": req.refresh_mode,
    }


@router.post("/legifrance/search")
async def search_legifrance(req: SearchLegifranceRequest):
    """Search Legifrance via PISTE API."""
    client = LegifranceClient()
    if not client.is_configured():
        raise HTTPException(status_code=503, detail="Legifrance PISTE credentials not configured")
    return await client.search(req.query, fond=req.fond, page_size=req.page_size)


@router.post("/legifrance/add")
async def add_source(req: AddSourceByIdRequest):
    """Add a Legifrance source to a collection.

    This registers the source for tracking. The actual fetch + indexation
    is triggered separately via POST /api/ingest/{collection}.
    """
    from app.services.collection_store import get_collection, update_collection

    config = await get_collection(req.collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")

    await update_collection(req.collection, {
        "source_type": "legifrance",
        "source_url": req.legifrance_id,
    })

    return {
        "status": "registered",
        "collection": req.collection,
        "legifrance_id": req.legifrance_id,
        "type": req.type,
        "refresh_mode": req.refresh_mode,
    }


@router.get("/legifrance/status/{collection}")
async def source_status(collection: str):
    """Check the Legifrance source status for a collection."""
    from app.services.collection_store import get_collection

    config = await get_collection(collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    return {
        "collection": collection,
        "legifrance_source_id": config.get("source_url") or None,
        "source_type": config.get("source_type", ""),
        "configured": config.get("source_type") == "legifrance",
    }


# ============================================================
# Suite Numerique Drive source
# ============================================================


class AddDriveSourceRequest(BaseModel):
    collection: str
    folder_id: str
    folder_title: str = ""


async def _drive_client():
    """Build a DriveConnector-friendly client with a fresh service token."""
    from app.services.connectors.drive import DriveClient
    from app.services.keycloak_client import get_service_token

    if not settings.drive_url or not settings.drive_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Drive n'est pas configure (DRIVE_URL / DRIVE_CLIENT_SECRET manquants).",
        )
    try:
        token = await get_service_token(
            settings.drive_client_id, settings.drive_client_secret
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Echec auth Keycloak client_credentials: {e.response.status_code}",
        )
    return DriveClient(settings.drive_url, token)


def _map_drive_item(raw: dict) -> dict:
    """Minimal representation of a Drive item for the frontend picker."""
    return {
        "id": raw.get("id"),
        "title": raw.get("title", "") or raw.get("filename", ""),
        "type": (raw.get("type") or "FILE").upper(),
        "updated_at": raw.get("updated_at", ""),
        "mimetype": raw.get("mimetype", ""),
        "size": raw.get("size", 0) or 0,
    }


@router.get("/drive/folders")
async def list_drive_folders(
    parent_id: str | None = Query(
        default=None,
        description="Parent folder id. Omit to list root items the service account can see.",
    ),
):
    """List children of a Drive folder (for the wizard picker).

    Returns a mix of folders and files so the user can see what's inside
    before picking a target folder to index. The frontend can filter on
    `type == "FOLDER"` for pure navigation.
    """
    client = await _drive_client()
    try:
        if parent_id:
            data = await client.list_children(parent_id)
        else:
            # No parent_id = service-account root view via /items/ (paginated)
            resp = await client._client.get("/items/")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Drive API {e.response.status_code} sur /items/{parent_id or ''}",
        )
    finally:
        await client.close()

    results = data.get("results", []) if isinstance(data, dict) else data
    return {
        "parent_id": parent_id,
        "items": [_map_drive_item(r) for r in (results or [])],
    }


@router.get("/drive/status/{collection}")
async def drive_status(collection: str):
    from app.services.collection_store import get_collection

    config = await get_collection(collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    cfg = json.loads(config.get("source_config_json") or "{}")
    return {
        "collection": collection,
        "configured": config.get("source_type") == "drive",
        "folder_id": cfg.get("folder_id"),
        "folder_title": cfg.get("folder_title"),
        "drive_url": cfg.get("drive_url"),
        "last_sync_at": cfg.get("last_sync_at"),
    }


async def _ingest_drive_folder(collection: str, folder_id: str) -> list[str]:
    """Pull every file of a Drive folder (recursive) and hand each one to the
    existing ingest pipeline. Returns the list of job_ids created.
    """
    from app.routers.ingest import _ingest_content
    from app.services.connectors.drive import DriveConnector
    from app.services.keycloak_client import get_service_token

    token = await get_service_token(settings.drive_client_id, settings.drive_client_secret)
    connector = DriveConnector(settings.drive_url, token, folder_id)
    try:
        docs = await connector.list_documents()
        job_ids: list[str] = []
        for doc in docs:
            try:
                content, filename = await connector.fetch_document(doc.id)
            except Exception as e:
                logger.warning("drive fetch failed for %s: %s", doc.id, e)
                continue
            try:
                result = await _ingest_content(
                    collection=collection,
                    filename=filename,
                    content=content,
                    strategy="auto",
                    sensitivity="public",
                    source_path=doc.url,
                )
                if "job_id" in result:
                    job_ids.append(result["job_id"])
            except Exception as e:
                logger.warning("drive ingest failed for %s: %s", filename, e)
        return job_ids
    finally:
        await connector.close()


@router.post("/drive/add")
async def add_drive_source(req: AddDriveSourceRequest):
    """Register a Drive folder as the source of a collection and kick off the
    initial import. Returns immediately; each file is indexed as a separate
    async job trackable via /api/ingest/jobs/{job_id}.
    """
    from app.services.collection_store import get_collection, update_collection

    if not settings.drive_url or not settings.drive_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Drive n'est pas configure (DRIVE_URL / DRIVE_CLIENT_SECRET manquants).",
        )

    collection = await get_collection(req.collection)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")

    # Resolve the folder (will 404 if invalid, auth fail, etc.)
    client = await _drive_client()
    try:
        folder = await client.get_item(req.folder_id)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 404:
            raise HTTPException(status_code=404, detail=f"Drive folder '{req.folder_id}' not found")
        raise HTTPException(status_code=502, detail=f"Drive API error {code}")
    finally:
        await client.close()

    folder_title = req.folder_title or folder.get("title") or folder.get("filename") or req.folder_id
    source_config = {
        "folder_id": req.folder_id,
        "folder_title": folder_title,
        "drive_url": settings.drive_url,
        "last_sync_at": None,
    }
    await update_collection(req.collection, {
        "source_type": "drive",
        "source_url": f"{settings.drive_url}/items/{req.folder_id}",
        "source_config_json": json.dumps(source_config),
    })

    # Fire-and-forget initial import — jobs are tracked in the DB.
    task = asyncio.create_task(_ingest_drive_folder(req.collection, req.folder_id))
    # Keep a reference so the task isn't GC'd prematurely.
    asyncio.get_running_loop()._drive_import_tasks = getattr(
        asyncio.get_running_loop(), "_drive_import_tasks", []
    ) + [task]

    return {
        "status": "registered",
        "collection": req.collection,
        "folder_id": req.folder_id,
        "folder_title": folder_title,
        "import_started": True,
    }


@router.post("/drive/sync/{collection}")
async def sync_drive_source(collection: str):
    """Delta-sync: re-ingest files modified since the last sync. Blocks until
    all new/modified files have been queued. V2 will replace this with a
    cron."""
    from app.services.collection_store import get_collection, update_collection
    from app.services.connectors.drive import DriveConnector
    from app.services.keycloak_client import get_service_token
    from app.routers.ingest import _ingest_content
    from app.models.db import utcnow

    config = await get_collection(collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    if config.get("source_type") != "drive":
        raise HTTPException(status_code=400, detail="Collection source is not Drive")

    cfg = json.loads(config.get("source_config_json") or "{}")
    folder_id = cfg.get("folder_id")
    since = cfg.get("last_sync_at") or ""

    token = await get_service_token(settings.drive_client_id, settings.drive_client_secret)
    connector = DriveConnector(settings.drive_url, token, folder_id)
    try:
        updated = await connector.check_updates(since)
        job_ids: list[str] = []
        for doc in updated:
            content, filename = await connector.fetch_document(doc.id)
            result = await _ingest_content(
                collection=collection, filename=filename, content=content,
                strategy="auto", sensitivity="public", source_path=doc.url,
            )
            if "job_id" in result:
                job_ids.append(result["job_id"])
    finally:
        await connector.close()

    cfg["last_sync_at"] = utcnow().isoformat()
    await update_collection(collection, {"source_config_json": json.dumps(cfg)})

    return {
        "status": "synced",
        "collection": collection,
        "files_updated": len(updated),
        "job_ids": job_ids,
        "last_sync_at": cfg["last_sync_at"],
    }
