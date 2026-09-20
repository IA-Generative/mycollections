"""MyRAG (beta) — Front augmente DSFR pour OpenRAG."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.services import capacites
from app.routers import ingest, collections, sync, graph, articles, sources, feedback, publication, playground, playground_bank, qr_cache_router, eval_datasets
from app.routers import accueil as accueil_routeur
from app.routers import amorces, bus, categories, collectif, corpus, demandes, fiches, guide

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

# Origines explicites si configurées (credentials autorisés) ; sinon repli sur
# '*' SANS credentials — combo '*' + credentials interdit par la spec et risqué.
_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=bool(_cors_origins),
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


from app.auth import AUTH_REQUIRED

# Routes XHR (le front attache un Bearer via useApi) → garde JWT activable par
# AUTH_ENABLED. Exemptés : graph/articles (HTML servi en iframe/lien direct,
# sans Authorization possible), feedback (écritures externes possibles) et les
# proxys admin-token (liens ouverts dans un nouvel onglet) — cf. risques résiduels.
app.include_router(ingest.router, dependencies=AUTH_REQUIRED)
app.include_router(collections.router, dependencies=AUTH_REQUIRED)
app.include_router(sync.router, dependencies=AUTH_REQUIRED)
app.include_router(graph.router)
app.include_router(articles.router)
app.include_router(sources.router, dependencies=AUTH_REQUIRED)
app.include_router(feedback.router)
app.include_router(publication.router, dependencies=AUTH_REQUIRED)
app.include_router(playground.router, dependencies=AUTH_REQUIRED)
app.include_router(playground_bank.router, dependencies=AUTH_REQUIRED)
app.include_router(qr_cache_router.router, dependencies=AUTH_REQUIRED)
app.include_router(eval_datasets.router, dependencies=AUTH_REQUIRED)
# Le collectif (ADR-0001) : demandes, circuit d'une collection, amorces.
app.include_router(demandes.router, dependencies=AUTH_REQUIRED)
app.include_router(collectif.router, dependencies=AUTH_REQUIRED)
app.include_router(corpus.router, dependencies=AUTH_REQUIRED)
app.include_router(amorces.router, dependencies=AUTH_REQUIRED)
app.include_router(guide.router, dependencies=AUTH_REQUIRED)
app.include_router(categories.router, dependencies=AUTH_REQUIRED)
app.include_router(accueil_routeur.router, dependencies=AUTH_REQUIRED)
app.include_router(fiches.router, dependencies=AUTH_REQUIRED)
# Le bus de la bêta : une machine, authentifiée par secret partagé — pas de jeton d'utilisateur.
app.include_router(bus.router)


@app.get("/api/config")
async def get_config():
    return {
        "app_title": settings.app_title,
        "openrag_url": settings.openrag_url,
        "graphrag_viewer_url": settings.graphrag_viewer_url,
        "myrag_public_url": settings.myrag_public_url,
        "drive_url": settings.drive_url,
        # Le collectif : les drapeaux et le seuil lus chez le menu commun (cache court,
        # jamais bloquant). L'écran lit aussi /_beta/capacites.json en même origine ;
        # ceci est son repli, et la valeur que le SERVEUR applique.
        **{k: v for k, v in (await capacites.lire_async()).items() if k in ("demandes", "signalements", "seuil_chantier")},
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


from app.services.morceau import decouper_morceau as _decouper_morceau  # noqa: E402


def _paragraphes_html(texte: str) -> str:
    """Texte brut → paragraphes HTML : tout est échappé, puis les adresses web
    deviennent des liens. Pas de moteur Markdown ici : la page reste autonome."""
    import html as _h
    import re
    blocs = [b.strip() for b in re.split(r"\n\s*\n", texte or "") if b.strip()]
    rendus = []
    for bloc in blocs:
        sur = _h.escape(bloc)
        sur = re.sub(
            r"(https?://[^\s<>\"']+[^\s<>\"'.,;:!?)])",
            r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
            sur,
        )
        rendus.append(f"<p>{sur}</p>")
    return "\n".join(rendus)


def _extract_render_html(payload: dict | None, chunk_id: str, raw: bytes, status: int) -> str:
    """Rend un morceau en page HTML autonome et lisible.

    Cette page s'ouvre dans un onglet neuf (« Ouvrir dans un onglet », Ctrl-clic
    sur une puce, lien cité depuis le chat) : pas de lien « Retour », il n'y a
    pas d'historique à remonter. Le texte est débarrassé de ses balises
    techniques et mis en paragraphes ; le résumé du document passe en encart.

    En cas d'échec d'OpenRAG (statut ≥ 400 ou réponse non JSON), on montre le
    statut et le début de la réponse brute, pour garder un indice.
    """
    import html as _h
    title = f"Extrait · {chunk_id[:12]}…"
    if status >= 400 or payload is None:
        body = (
            f"<h1>Extrait indisponible</h1>"
            f"<p class='meta'>OpenRAG a renvoyé HTTP {status}.</p>"
            f"<pre class='brut'>{_h.escape(raw.decode('utf-8', 'replace')[:2000])}</pre>"
        )
    else:
        content = payload.get("page_content") or payload.get("content") or payload.get("text") or ""
        contexte, fichier, corps = _decouper_morceau(str(content))
        source = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        lire = lambda k: payload.get(k) or source.get(k)  # noqa: E731
        fichier = str(lire("original_filename") or lire("filename") or fichier or "")
        meta_parts = []
        if fichier:
            meta_parts.append(f"<strong>Fichier</strong> : {_h.escape(fichier)}")
        if lire("page") not in (None, ""):
            meta_parts.append(f"<strong>Page</strong> : {_h.escape(str(lire('page')))}")
        if lire("partition"):
            meta_parts.append(f"<strong>Collection</strong> : {_h.escape(str(lire('partition')))}")
        if fichier:
            title = f"{fichier} · extrait"
        body = (
            "<p class='sur-titre'>Extrait de source</p>"
            f"<h1>{_h.escape(fichier or 'Extrait')}</h1>"
            + (f"<p class='meta'>{' &middot; '.join(meta_parts)}</p>" if meta_parts else "")
            + f"<div class='texte'>{_paragraphes_html(corps) or '<p><em>(extrait vide)</em></p>'}</div>"
            + (
                "<aside class='contexte'><p class='contexte-titre'>À propos du document "
                "<span>— résumé automatique</span></p>"
                f"{_paragraphes_html(contexte)}</aside>" if contexte else ""
            )
        )
    # CSS en ligne : la page est autonome, sans ressource DSFR à aller chercher
    # sur l'hôte du frontend.
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_h.escape(title)}</title>
<style>
  body {{ font-family: Marianne, -apple-system, "Segoe UI", system-ui, Arial, sans-serif;
           max-width: 760px; margin: 2.5rem auto; padding: 0 1.2rem; color: #161616; line-height: 1.6; }}
  .sur-titre {{ margin: 0; font-size: 0.8rem; font-weight: 700; letter-spacing: 0.04em;
                text-transform: uppercase; color: #000091; }}
  h1 {{ font-size: 1.4rem; line-height: 1.3; margin: 0.2rem 0 0.5rem; word-break: break-word; }}
  .meta {{ margin: 0 0 1.5rem; padding-bottom: 0.8rem; border-bottom: 1px solid #ddd;
           font-size: 0.85rem; color: #666; }}
  .texte p {{ margin: 0 0 1rem; white-space: pre-line; word-break: break-word; }}
  a {{ color: #000091; }}
  .contexte {{ margin-top: 2rem; padding: 0.8rem 1.1rem; background: #f6f6f6;
               border-left: 3px solid #cecece; font-size: 0.9rem; color: #3a3a3a; }}
  .contexte p {{ margin: 0 0 0.4rem; }}
  .contexte p:last-child {{ margin-bottom: 0; }}
  .contexte-titre {{ font-size: 0.8rem; font-weight: 700; }}
  .contexte-titre span {{ font-weight: 400; color: #666; }}
  .brut {{ background: #f6f6f6; padding: 1rem 1.2rem; border-left: 3px solid #ce0500;
           white-space: pre-wrap; word-break: break-word; font-size: 0.85rem; }}
</style></head>
<body>{body}</body></html>"""


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
    from app.security_utils import reject_path_traversal
    reject_path_traversal(chunk_id, field="chunk_id")
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
    from app.security_utils import reject_path_traversal
    reject_path_traversal(file_id, field="file_id")
    headers = {"Authorization": f"Bearer {settings.openrag_admin_token}"}
    url = f"{settings.openrag_url.rstrip('/')}/file/{file_id}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        upstream = await client.get(url, headers=headers)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
    )


@app.get("/api/owui/probe")
async def owui_probe():
    """Diagnostic endpoint for the admin API key.

    Returns only the HTTP status of the OWUI calls that /publish would make,
    to pin down whether a 401 is "bad key", "key valid but not admin", "wrong
    URL", or "OWUI unreachable".

    Does not expose the key (not even a prefix) nor any upstream response body.
    """
    from app.services.owui_client import OwuiClient, OwuiAdminUnavailable
    import httpx
    try:
        client = OwuiClient()
    except OwuiAdminUnavailable as e:
        return {"ok": False, "stage": "config", "detail": str(e)}
    out = {
        "base_url": client.base_url,
        "key_set": bool(client.api_key),
        "calls": [],
    }
    probes = [
        ("GET", "/api/v1/auths", None),              # whoami — confirms key validity
        ("GET", "/api/v1/users/", None),             # admin-only — confirms admin role
        ("GET", "/api/v1/models/model", {"id": "openrag-bas"}),
        ("GET", "/api/models", None),                # full model list incl. discovered base models
        ("GET", "/openai/models", None),             # OWUI's OpenAI proxy listing
    ]
    async with httpx.AsyncClient(timeout=10.0) as h:
        for method, path, params in probes:
            try:
                r = await h.request(method, f"{client.base_url}{path}",
                                    params=params, headers=client._headers())
                out["calls"].append({
                    "method": method, "path": path,
                    "status": r.status_code,
                    "ok": r.status_code < 400,
                })
            except Exception:
                out["calls"].append({"method": method, "path": path, "error": "request failed"})
    return out


@app.get("/api/openrag/static/{filepath:path}")
async def openrag_static_proxy(filepath: str, raw: bool = False):
    """Proxy for OpenRAG's /static/<hashname> URLs — what source.file_url
    points to for whole-document access. Auth-protected on OpenRAG's side
    (redirects to /auth/login for anonymous callers), relayed here with
    the stored admin token.

    Preserves the upstream content-type so the browser opens PDFs inline
    (application/pdf), images inline, etc.
    """
    import httpx
    from fastapi import Response
    from app.security_utils import reject_path_traversal
    reject_path_traversal(filepath, field="filepath")
    headers = {"Authorization": f"Bearer {settings.openrag_admin_token}"}
    url = f"{settings.openrag_url.rstrip('/')}/static/{filepath}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        upstream = await client.get(url, headers=headers)
    # /static ignore le jeton et renvoie vers son SSO (302 /auth/login) — suivi,
    # c'était une page Keycloak servie en 200 au lieu du document. Le morceau
    # porte le même identifiant : on le rend à la place, plutôt qu'une page de
    # connexion à un service que l'utilisateur ne connaît pas.
    if upstream.status_code in (301, 302, 303, 307, 308) or \
            upstream.headers.get("content-type", "").startswith("text/html"):
        return await openrag_extract_proxy(filepath, raw=raw)
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
