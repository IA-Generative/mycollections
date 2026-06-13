"""Sources router — Legifrance + Drive source management + URL checking."""

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.services.legifrance_client import LegifranceClient, parse_legifrance_url
from app.security_utils import assert_public_http_url, ssrf_request_guard

# Hook anti-SSRF appliqué à tous les fetch d'URL fournies par l'utilisateur.
_SSRF_HOOKS = {"request": [ssrf_request_guard]}

# Safety caps for the synchronous fetch in /drive/add — protect against both
# ingress timeouts and OOM. If a user really needs more, they can fractionner.
DRIVE_MAX_FILES = 500
DRIVE_MAX_TOTAL_BYTES = 500 * 1024 * 1024   # 500 MB


def _bearer(authorization: str | None) -> str:
    """Extract the raw Bearer token from an Authorization header, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header (expected 'Bearer <token>').",
        )
    return authorization.split(" ", 1)[1].strip()

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
        assert_public_http_url(url)
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, event_hooks=_SSRF_HOOKS) as client:
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
        assert_public_http_url(url)
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, event_hooks=_SSRF_HOOKS) as client:
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


def _drive_403_detail() -> str:
    """Message for a Drive 403. Two realistic causes, indistinguishable from
    the response: the token is missing the `mycollections-drive` audience
    (Keycloak mapper not applied yet — reconnecting mints a fresh one), or
    the user has never logged into Drive so its local DB has no entry."""
    return (
        "Drive a refuse votre acces (403). Essayez dans l'ordre : "
        "1) deconnectez-vous puis reconnectez-vous ici pour rafraichir votre "
        f"jeton ; 2) si le probleme persiste, connectez-vous une fois sur "
        f"{settings.drive_url} (instantane) puis revenez."
    )


def _drive_client_for_user(user_token: str):
    """Build a DriveClient that relays the user's access token.

    Drive sees the call as made by the real user → the Resource Server
    filter surfaces only the folders the user can see on Drive. No service
    account involved in this path.
    """
    from app.services.connectors.drive import DriveClient

    if not settings.drive_url:
        raise HTTPException(
            status_code=503,
            detail="Drive n'est pas configure (DRIVE_URL manquant).",
        )
    return DriveClient(settings.drive_url, user_token)


async def _drive_service_client():
    """Fallback: build a DriveClient with a service-account token.

    Used only by paths where no user is in session (e.g. scheduled sync).
    """
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
        description="Parent folder id. Omit to list the user's root items.",
    ),
    authorization: str | None = Header(default=None),
):
    """List children of a Drive folder (for the wizard picker).

    Uses the caller's OIDC token (impersonation) so Drive returns only the
    folders that specific user can see — no leaking of other users' shares.
    Returns a mix of folders and files so the user can see what's inside
    before picking a target folder to index.
    """
    client = _drive_client_for_user(_bearer(authorization))
    try:
        if parent_id:
            data = await client.list_children(parent_id)
        else:
            resp = await client._client.get("/items/")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 403:
            raise HTTPException(status_code=403, detail=_drive_403_detail())
        raise HTTPException(
            status_code=401 if code == 401 else 502,
            detail=f"Drive API {code} sur /items/{parent_id or ''}",
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


async def _ingest_downloaded_files(
    collection: str, files: list[tuple[bytes, str, str]]
) -> list[str]:
    """Ingest already-downloaded bytes into the standard pipeline, one job
    per file. Runs in the background — at this point the user token is no
    longer needed because the bytes are in memory.

    ``files`` is a list of ``(content, filename, source_url)`` tuples.
    """
    from app.routers.ingest import _ingest_content

    job_ids: list[str] = []
    for content, filename, src_url in files:
        try:
            result = await _ingest_content(
                collection=collection, filename=filename, content=content,
                strategy="auto", sensitivity="public", source_path=src_url,
            )
            if "job_id" in result:
                job_ids.append(result["job_id"])
        except Exception as e:
            logger.warning("drive ingest failed for %s: %s", filename, e)
    return job_ids


@router.post("/drive/add")
async def add_drive_source(
    req: AddDriveSourceRequest,
    authorization: str | None = Header(default=None),
):
    """Register a Drive folder as the source of a collection and kick off the
    initial import. Downloads every file synchronously in this call using
    the caller's user token (Drive ACL is honored), then hands the bytes to
    the ingest pipeline in the background. The user's access token only has
    to live through the download phase.

    Refuses folders exceeding DRIVE_MAX_FILES or DRIVE_MAX_TOTAL_BYTES (413).
    """
    from app.services.collection_store import get_collection, update_collection
    from app.services.connectors.drive import DriveConnector

    user_token = _bearer(authorization)

    collection = await get_collection(req.collection)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")

    # Resolve the folder with the user's token (404 if user can't see it).
    probe = _drive_client_for_user(user_token)
    try:
        folder = await probe.get_item(req.folder_id)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 403:
            raise HTTPException(status_code=403, detail=_drive_403_detail())
        if code == 401:
            raise HTTPException(status_code=401, detail="Drive refuse votre token (expiré ou invalide).")
        if code == 404:
            raise HTTPException(status_code=404, detail=f"Drive folder '{req.folder_id}' not found")
        raise HTTPException(status_code=502, detail=f"Drive API error {code}")
    finally:
        await probe.close()

    folder_title = req.folder_title or folder.get("title") or folder.get("filename") or req.folder_id

    # Sync download — while the user's access token is still valid.
    connector = DriveConnector(settings.drive_url, user_token, req.folder_id)
    downloaded: list[tuple[bytes, str, str]] = []
    total_bytes = 0
    try:
        docs = await connector.list_documents()
        if len(docs) > DRIVE_MAX_FILES:
            raise HTTPException(
                status_code=413,
                detail=f"Dossier trop volumineux: {len(docs)} fichiers (max {DRIVE_MAX_FILES}). Fractionnez le dossier.",
            )
        for doc in docs:
            try:
                content, filename = await connector.fetch_document(doc.id)
            except httpx.HTTPStatusError as e:
                logger.warning("drive fetch %s: HTTP %s", doc.id, e.response.status_code)
                continue
            except Exception as e:
                logger.warning("drive fetch %s: %s", doc.id, e)
                continue
            total_bytes += len(content)
            if total_bytes > DRIVE_MAX_TOTAL_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Dossier trop volumineux: >{DRIVE_MAX_TOTAL_BYTES // (1024*1024)} Mo cumulés. Fractionnez.",
                )
            downloaded.append((content, filename, doc.url))
    finally:
        await connector.close()

    # Persist source config.
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

    # Fire-and-forget async ingest from bytes already in memory — no Drive
    # calls from here on, so the user's token can expire without impact.
    task = asyncio.create_task(_ingest_downloaded_files(req.collection, downloaded))
    loop = asyncio.get_running_loop()
    loop._drive_import_tasks = getattr(loop, "_drive_import_tasks", []) + [task]

    return {
        "status": "registered",
        "collection": req.collection,
        "folder_id": req.folder_id,
        "folder_title": folder_title,
        "files_count": len(downloaded),
        "total_bytes": total_bytes,
        "import_started": True,
    }


@router.post("/drive/sync/{collection}")
async def sync_drive_source(
    collection: str,
    authorization: str | None = Header(default=None),
):
    """Delta-sync: re-ingest files modified since the last sync. Uses the
    caller's user token for impersonation (same ACL as /drive/add)."""
    from app.services.collection_store import get_collection, update_collection
    from app.services.connectors.drive import DriveConnector
    from app.routers.ingest import _ingest_content
    from app.models.db import utcnow

    user_token = _bearer(authorization)

    config = await get_collection(collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    if config.get("source_type") != "drive":
        raise HTTPException(status_code=400, detail="Collection source is not Drive")

    cfg = json.loads(config.get("source_config_json") or "{}")
    folder_id = cfg.get("folder_id")
    since = cfg.get("last_sync_at") or ""

    connector = DriveConnector(settings.drive_url, user_token, folder_id)
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
