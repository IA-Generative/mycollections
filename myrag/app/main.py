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


@app.get("/api/openrag/extract/{chunk_id}")
async def openrag_extract_proxy(chunk_id: str):
    """Proxy for OpenRAG's /extract/{chunk_id} and /file/{id} endpoints.

    Those endpoints require a Bearer admin token; a bare link opened in a
    new browser tab would send no Authorization header and get 401. This
    relays the request server-side with the stored admin token so the
    browser sees plain content.

    Chunk URL and file URL are both under OpenRAG's /extract path family in
    practice — /extract/<chunk_uuid> returns the chunk snippet, /extract/
    /file/<file_id> or a direct /file/<id> exposes the source file. We
    forward the raw path so both shapes work.
    """
    import httpx
    from fastapi import Response
    headers = {"Authorization": f"Bearer {settings.openrag_admin_token}"}
    url = f"{settings.openrag_url.rstrip('/')}/extract/{chunk_id}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        upstream = await client.get(url, headers=headers)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/plain"),
    )


@app.get("/api/openrag/file/{file_id}")
async def openrag_file_proxy(file_id: str):
    """Same as /api/openrag/extract but for /file/<id> URLs that OpenRAG
    emits for whole-document downloads.
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
