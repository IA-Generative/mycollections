"""MyRAG (beta) — Front augmente DSFR pour OpenRAG."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.routers import ingest, collections, sync, graph, articles, sources, feedback, publication, playground, playground_bank, qr_cache_router, eval_datasets

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import models so tables are registered
    import app.models.db  # noqa: F401
    await init_db()
    yield


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_title,
        "version": settings.app_version,
    }


@app.get("/")
async def root():
    return JSONResponse(
        content={
            "app": settings.app_title,
            "version": settings.app_version,
            "docs": "/docs",
        }
    )


app.include_router(ingest.router)
app.include_router(collections.router)
app.include_router(sync.router)
app.include_router(graph.router)
app.include_router(articles.router)
app.include_router(sources.router)
app.include_router(feedback.router)
app.include_router(publication.router)
app.include_router(playground.router)
app.include_router(playground_bank.router)
app.include_router(qr_cache_router.router)
app.include_router(eval_datasets.router)


@app.get("/api/config")
async def get_config():
    return {
        "app_title": settings.app_title,
        "openrag_url": settings.openrag_url,
        "graphrag_viewer_url": settings.graphrag_viewer_url,
        "myrag_public_url": settings.myrag_public_url,
        "drive_url": settings.drive_url,
    }


@app.get("/api/openrag/health")
async def openrag_health():
    """Proxy for OpenRAG's health_check. Browsers can't reach OpenRAG
    directly (CORS) so the layout status badge calls this instead.
    """
    from app.services.openrag_client import OpenRAGClient
    client = OpenRAGClient(timeout=5.0)
    ok = await client.health_check()
    return {"status": "up" if ok else "down", "openrag_url": settings.openrag_url}


def _extract_render_html(payload: dict | None, chunk_id: str, raw: bytes, status: int) -> str:
    """Render a chunk payload as a minimal DSFR-flavored HTML page.

    The user opens the proxy URL in a new tab. Raw JSON with literal \\n
    escapes is unreadable; we extract page_content + metadata and wrap in
    a monospace pre with whitespace preserved.

    Falls back to showing the upstream status + raw body on non-2xx or
    non-JSON responses so you still have a clue what went wrong.
    """
    import html as _h
    title = f"Extrait · {chunk_id[:12]}…"
    if status >= 400 or payload is None:
        body = (
            f"<h1 class='fr-h4'>Extrait indisponible</h1>"
            f"<p class='fr-text--sm'>OpenRAG a renvoye HTTP {status}.</p>"
            f"<pre class='myrag-extract__raw'>{_h.escape(raw.decode('utf-8', 'replace')[:2000])}</pre>"
        )
    else:
        content = payload.get("page_content") or payload.get("content") or payload.get("text") or ""
        meta_parts = []
        for k in ("original_filename", "filename", "page", "file_id", "chunk_id"):
            v = payload.get(k)
            if v:
                meta_parts.append(f"<strong>{_h.escape(str(k))}:</strong> {_h.escape(str(v))}")
        meta = " &middot; ".join(meta_parts) if meta_parts else ""
        body = (
            f"<h1 class='fr-h4'>Extrait de source</h1>"
            + (f"<p class='fr-text--sm' style='color:#666;'>{meta}</p>" if meta else "")
            + f"<pre class='myrag-extract__body'>{_h.escape(content)}</pre>"
        )
    # Inline CSS keeps this self-contained; no DSFR asset required (which
    # would need another roundtrip through the frontend host).
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>{_h.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, system-ui, sans-serif; max-width: 900px;
           margin: 2rem auto; padding: 0 1.2rem; color: #161616; line-height: 1.5; }}
  .fr-h4 {{ font-size: 1.25rem; margin: 0 0 0.6rem; }}
  pre {{ background: #f6f6f6; padding: 1rem 1.2rem; border-left: 3px solid #000091;
         border-radius: 4px; white-space: pre-wrap; word-break: break-word;
         font-size: 0.92rem; line-height: 1.55; }}
  .myrag-extract__raw {{ border-left-color: #ce0500; }}
  a.back {{ display: inline-block; margin-bottom: 1rem; color: #000091; text-decoration: none; }}
  a.back:hover {{ text-decoration: underline; }}
</style></head>
<body><a class="back" href="javascript:history.back()">&larr; Retour</a>{body}</body></html>"""


@app.get("/api/openrag/extract/{chunk_id}")
async def openrag_extract_proxy(chunk_id: str, raw: bool = False):
    """Proxy for OpenRAG's /extract/{chunk_id} endpoint.

    Those endpoints require a Bearer admin token; a bare link opened in a
    new browser tab would send no Authorization header and get 401. This
    relays the request server-side with the stored admin token.

    Default response is a minimal HTML page rendering page_content with
    whitespace preserved — opening the raw JSON (with \\n escapes) in a
    browser tab is unreadable. Pass ?raw=1 to get the upstream JSON as-is
    (useful for debugging or programmatic access).
    """
    import httpx
    import json as _json
    from fastapi import Response
    from fastapi.responses import HTMLResponse
    headers = {"Authorization": f"Bearer {settings.openrag_admin_token}"}
    url = f"{settings.openrag_url.rstrip('/')}/extract/{chunk_id}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        upstream = await client.get(url, headers=headers)
    if raw:
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/plain"),
        )
    payload = None
    try:
        payload = _json.loads(upstream.content)
    except Exception:
        payload = None
    return HTMLResponse(
        content=_extract_render_html(payload, chunk_id, upstream.content, upstream.status_code),
        status_code=upstream.status_code if upstream.status_code < 500 else 200,
    )


@app.get("/api/openrag/file/{file_id}")
async def openrag_file_proxy(file_id: str):
    """Proxy for OpenRAG's /file/<id> endpoint (rarely emitted in practice,
    but kept for completeness).
    """
    import httpx
    from fastapi import Response
    headers = {"Authorization": f"Bearer {settings.openrag_admin_token}"}
    url = f"{settings.openrag_url.rstrip('/')}/file/{file_id}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        upstream = await client.get(url, headers=headers)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
    )


@app.get("/api/openrag/static/{filepath:path}")
async def openrag_static_proxy(filepath: str):
    """Proxy for OpenRAG's /static/<hashname> URLs — what source.file_url
    points to for whole-document access. Auth-protected on OpenRAG's side
    (redirects to /auth/login for anonymous callers), relayed here with
    the stored admin token.

    Preserves the upstream content-type so the browser opens PDFs inline
    (application/pdf), images inline, etc.
    """
    import httpx
    from fastapi import Response
    headers = {"Authorization": f"Bearer {settings.openrag_admin_token}"}
    url = f"{settings.openrag_url.rstrip('/')}/static/{filepath}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        upstream = await client.get(url, headers=headers)
    # Preserve content-disposition so browsers can hint a filename on save.
    resp_headers = {}
    if "content-disposition" in upstream.headers:
        resp_headers["Content-Disposition"] = upstream.headers["content-disposition"]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers=resp_headers,
    )
