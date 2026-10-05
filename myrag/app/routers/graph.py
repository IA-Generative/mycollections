"""Graph router — article reference graph API + viewer."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.auth import AUTH_REQUIRED, CurrentUser, current_user
from app.routers._acces_navigateur import lecture_de_la_collection, lecture_du_corpus
from app.services import access
from app.services.collection_store import get_collection, update_collection
from app.services.graph_builder import GraphBuilder, GraphImportError

router = APIRouter(prefix="/graph", tags=["Graph"])

_builder = GraphBuilder()


async def config_du_visualiseur(corpus_id: str) -> dict:
    """Ce que le visualiseur doit savoir pour ouvrir l'assistant sur la collection.

    Le modèle n'est donné que si la collection est publiée À TOUS dans l'assistant : cette page est
    servie sans session (une iframe ne porte pas de jeton), elle ne dit donc rien qui ne soit déjà
    visible de tout compte de l'assistant.
    """
    from app.config import settings
    from app.database import async_session
    from app.models.db import Collection, Publication

    public = (settings.owui_public_url or "").strip().rstrip("/")
    modele = ""
    if public and corpus_id:
        async with async_session() as session:
            col = await session.get(Collection, corpus_id)
            pub = await session.get(Publication, corpus_id)
            if (col and pub and not col.archived_at and pub.state == "published"
                    and pub.alias_enabled and pub.visibility == "all"):
                modele = f"openrag-{col.name}"
    return {"openwebui_url": public, "assistant_model": modele}


def injecter_config(html: str, config: dict) -> str:
    """Pose `window.GRAPH_VIEWER_CONFIG` en tête de page. Tout `<` est écrit `\\u003c` : aucune
    valeur ne peut refermer la balise script, ni en ouvrir une."""
    import json
    charge = json.dumps(config, ensure_ascii=False).replace("<", "\\u003c")
    return html.replace("<body>", f"<body>\n  <script>window.GRAPH_VIEWER_CONFIG = {charge};</script>", 1)


@router.get("", response_class=HTMLResponse)
async def graph_viewer(
    corpus_id: str = Query("", description="Collection to display"),
    query: str = Query("", description="Focus query"),
):
    """Serve the Cytoscape.js graph viewer."""
    import os
    viewer_path = os.path.join(os.path.dirname(__file__), "..", "static", "graph_view.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="Graph viewer not found")
    with open(viewer_path) as f:
        return HTMLResponse(content=injecter_config(f.read(), await config_du_visualiseur(corpus_id)))


@router.get("/{collection}/lien")
async def lien_du_visualiseur(collection: str, user: CurrentUser = Depends(current_user)):
    """L'adresse du visualiseur pour cette collection, signée : la fiche l'ouvre dans une iframe,
    qui ne porte pas de jeton. Rendue seulement à qui lit la collection."""
    from urllib.parse import quote

    from app.routers._acces_navigateur import peut_lire
    from app.services import liens
    if not peut_lire(await get_collection(collection), collection, user):
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    url = f"/graph?corpus_id={quote(collection)}"
    return {"url": liens.signer(url, liens.portee_graphe(collection))}


@router.get("/data", dependencies=[Depends(lecture_du_corpus)])
async def graph_data(
    corpus_id: str = Query("", description="Collection name"),
    query: str = Query("", description="Search text to filter nodes"),
    max_nodes: int = Query(80, ge=5, le=500),
    min_weight: float = Query(0.0, ge=0.0),
    source_prefix: str = Query("", max_length=200, description="Partie du corpus (un Livre) à laquelle restreindre le graphe"),
):
    """Graph data in GraphDataResponse format (compatible with grafragexp Cytoscape.js viewer)."""
    if not corpus_id:
        raise HTTPException(status_code=400, detail="corpus_id is required")

    return _builder.to_graph_data_response(
        collection=corpus_id,
        query=query,
        max_nodes=max_nodes,
        min_weight=min_weight,
        source_prefix=source_prefix,
    )


@router.get("/{collection}/related", dependencies=[Depends(lecture_de_la_collection)])
async def related_articles(
    collection: str,
    article: str = Query(..., description="Article ID (e.g., L421-1)"),
    depth: int = Query(1, ge=0, le=5, description="Number of hops"),
):
    """Get a subgraph around a specific article."""
    subgraph = _builder.get_subgraph(collection, [article], depth=depth)
    if not subgraph:
        raise HTTPException(status_code=404, detail=f"No graph for collection '{collection}'")

    nodes = []
    for node_id, attrs in subgraph.nodes(data=True):
        nodes.append({
            "id": node_id,
            "label": attrs.get("label", node_id),
            "livre": attrs.get("livre", ""),
            "titre": attrs.get("titre", ""),
            "chapitre": attrs.get("chapitre", ""),
            "referenced_by": attrs.get("referenced_by", []),
            "is_focus": node_id == article,
        })

    edges = []
    for source, target, attrs in subgraph.edges(data=True):
        edges.append({
            "source": source,
            "target": target,
            "description": attrs.get("description", "cite"),
        })

    return {
        "focus": article,
        "depth": depth,
        "collection": collection,
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/config", dependencies=AUTH_REQUIRED)
async def graph_config():
    """Config for the graph viewer."""
    from app.config import settings
    return {
        "api_base_url": settings.myrag_public_url,
        "graphrag_viewer_url": settings.graphrag_viewer_url,
    }


async def _exiger_gestionnaire(collection: str, user: CurrentUser) -> dict | None:
    """Refuse (403) quiconque ne gère pas la collection ; renvoie sa fiche, ou None si elle n'en a pas.

    Une partition sans fiche reste reconstructible par un superadmin ou un membre de
    ``<collection>-admin`` : même tolérance que pour le prompt système.
    """
    fiche = await get_collection(collection)
    if not access.can_write(
        name=collection, created_by=(fiche or {}).get("created_by"),
        user_groups=user.groups, user_sub=user.sub,
    ):
        raise HTTPException(status_code=403, detail="Accès refusé à cette collection")
    return fiche


class GraphImportRequest(BaseModel):
    nodes: list[dict]
    edges: list[dict] = []


@router.put("/{collection}")
async def import_graph(
    collection: str, req: GraphImportRequest, user: CurrentUser = Depends(current_user)
):
    """Dépose un graphe construit hors de MyRAG (même forme que ``graph.json``).

    Réservé aux gestionnaires de la collection. Le graphe importé est protégé :
    ``POST /{collection}/build`` refuse de l'écraser sans ``force=true``.
    """
    fiche = await _exiger_gestionnaire(collection, user)
    if not fiche:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    try:
        graph = _builder.import_graph(collection, req.model_dump(), imported_by=user.sub)
    except GraphImportError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not fiche.get("graph_enabled"):
        await update_collection(collection, {"graph_enabled": True})
    return {
        "status": "imported",
        "collection": collection,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
    }


@router.post("/{collection}/build")
async def build_graph(
    collection: str,
    force: bool = Query(False, description="Écraser un graphe importé"),
    user: CurrentUser = Depends(current_user),
):
    """Build or rebuild the graph for a collection from its indexed chunks.

    Réservé aux gestionnaires : la reconstruction remplace le graphe sur disque, et
    ``force=true`` écrase même un graphe importé.
    """
    from app.services.openrag_client import OpenRAGClient

    await _exiger_gestionnaire(collection, user)

    if _builder.is_imported(collection) and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Le graphe de '{collection}' a été importé ; force=true pour le reconstruire.",
        )

    client = OpenRAGClient()

    # Les morceaux se LISTENT, ils ne se cherchent pas : une recherche sémantique « * » est
    # vidée par le seuil de pertinence d'OpenRAG (d'où l'ancien 404 « No documents » après une
    # indexation réussie). Chaque article est déposé comme un fichier « Article-<id>.md ».
    try:
        fichiers = await client.list_files(collection)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OpenRAG n'a pas répondu à la liste des documents : {e}")

    articles = []
    for f in fichiers:
        nom = str(f.get("original_filename") or f.get("filename") or "")
        if nom.startswith(("Article-", "Article_")) and f.get("file_id"):
            articles.append((nom, str(f["file_id"]), f))
    if not articles:
        # Rien à construire : surtout ne pas écraser un graphe existant par un graphe vide.
        raise HTTPException(status_code=422, detail=(
            "Aucun article dans cette collection : le graphe relie des articles de code découpés "
            "un par un (« Article L… »). Choisissez le découpage par article, ou importez un graphe."))

    import asyncio
    from app.services.graph_builder import extract_references
    limite = asyncio.Semaphore(8)

    async def lire(nom: str, file_id: str, meta: dict) -> dict:
        async with limite:
            contenu = await client.get_file_content(collection, file_id)
        article = nom.replace("Article-", "").replace("Article_", "").removesuffix(".md")
        references = [r for r in extract_references(contenu or "") if r != article]
        return {
            "content": contenu or "",
            "filename": nom,
            "metadata": {
                "article": article,
                "livre": meta.get("livre", ""), "titre": meta.get("titre", ""),
                "chapitre": meta.get("chapitre", ""), "references": references,
                "parent_path": meta.get("parent_path", ""),
            },
        }

    chunks = await asyncio.gather(*(lire(n, i, m) for n, i, m in articles))

    # Build and save graph
    graph = _builder.build(collection, chunks)
    _builder.save(collection)

    return {
        "status": "built",
        "collection": collection,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
    }


@router.post("/{collection}/summarize")
async def summarize_articles(
    collection: str,
    threshold: int | None = Query(None, description="Seuil de longueur (défaut : réglage de la collection)"),
    user: CurrentUser = Depends(current_user),
):
    """Résume par l'IA les articles longs du graphe, avec le modèle d'OpenRAG de la collection.

    Réservé aux gestionnaires : la route réécrit le graphe sur disque. Les articles plus courts
    que le seuil gardent leur aperçu brut.
    """
    config = await _exiger_gestionnaire(collection, user)
    if config and not config.get("ai_summary_enabled") and threshold is None:
        return {
            "status": "disabled",
            "detail": f"Les résumés IA sont désactivés pour « {collection} » : activez-les dans ses réglages.",
        }

    effective_threshold = threshold or ((config or {}).get("ai_summary_threshold") or 1000)

    graph = _builder.get(collection)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Pas encore de graphe pour « {collection} » : construisez-le d'abord.")

    long_articles = [n for n, d in graph.nodes(data=True) if d.get("content_full_length", 0) > effective_threshold]
    if not long_articles:
        return {"status": "nothing_to_summarize", "threshold": effective_threshold}

    # Le texte complet des articles : relu dans OpenRAG, comme à la construction (avant : cherché
    # sous data_dir/<collection>/*.md, où rien n'est jamais écrit).
    from app.services.openrag_client import OpenRAGClient
    client = OpenRAGClient()
    chunks = []
    for f in await client.list_files(collection):
        nom = str(f.get("original_filename") or f.get("filename") or "")
        article = nom.replace("Article-", "").replace("Article_", "").removesuffix(".md")
        if article in long_articles and f.get("file_id"):
            chunks.append({"content": await client.get_file_content(collection, str(f["file_id"])),
                           "metadata": {"article": article}})

    result = await _builder.summarize_long_articles(collection=collection, chunks=chunks, threshold=effective_threshold)
    return {
        "status": "done",
        "collection": collection,
        "threshold": effective_threshold,
        "ai_summary_enabled": bool((config or {}).get("ai_summary_enabled", True)),
        "articles_needing_summary": len(long_articles),
        **result,
    }

