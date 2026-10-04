"""Articles router — serve article views as HTML (iframe-friendly)."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from app.routers._acces_navigateur import lecture_de_la_collection
from app.services import liens
from app.services.graph_builder import GraphBuilder

# Servies sans jeton (lien, iframe) : la garde accepte une collection publiée à tous, un lien
# signé ou un jeton qui lit la collection (app/routers/_acces_navigateur.py).
router = APIRouter(prefix="/articles", tags=["Articles"], dependencies=[Depends(lecture_de_la_collection)])

_builder = GraphBuilder()

# Jinja2 templates
_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


@router.get("/{collection}/{article_id}", response_class=HTMLResponse)
async def view_article(collection: str, article_id: str, request: Request):
    """Render an article as HTML (iframe-friendly, DSFR styling)."""
    graph = _builder.get(collection)

    if not graph or article_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found in '{collection}'")

    node = graph.nodes[article_id]

    # Get outgoing references (articles this one cites)
    references = list(graph.successors(article_id))

    # Get incoming references (articles that cite this one)
    referenced_by = node.get("referenced_by", [])

    from app.services.collection_store import get_collection
    from app.services.nommage import titre_de

    fiche = await get_collection(collection)
    template = _env.get_template("article_view.html")
    html = template.render(
        collection=collection,
        collection_titre=titre_de(fiche or {"name": collection}),
        article_id=article_id,
        content=node.get("content_preview", ""),
        livre=node.get("livre", ""),
        titre=node.get("titre", ""),
        chapitre=node.get("chapitre", ""),
        sensitivity=node.get("sensitivity", "public"),
        references=references,
        referenced_by=referenced_by,
        # Les liens de la page portent la signature reçue, pour rester ouvrables.
        sig_q=_signature_recue(request, collection),
    )
    return HTMLResponse(content=html)


@router.get("/{collection}/{article_id}/json")
async def article_json(collection: str, article_id: str):
    """Get article data as JSON."""
    graph = _builder.get(collection)

    if not graph or article_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found")

    node = dict(graph.nodes[article_id])
    references = list(graph.successors(article_id))
    referenced_by = node.get("referenced_by", [])

    return {
        "article_id": article_id,
        "collection": collection,
        "label": node.get("label", article_id),
        "livre": node.get("livre", ""),
        "titre": node.get("titre", ""),
        "chapitre": node.get("chapitre", ""),
        "content": node.get("content_preview", ""),
        "references": references,
        "referenced_by": referenced_by,
        "degree": graph.degree(article_id),
    }


def _signature_recue(request: Request, collection: str) -> str:
    """`&exp=…&sig=…` si la page a été ouverte par un lien signé encore valide, sinon vide."""
    from urllib.parse import urlencode
    q = request.query_params
    if liens.valide(liens.portee_graphe(collection), q.get("exp"), q.get("sig")):
        return "&" + urlencode({"exp": q["exp"], "sig": q["sig"]})
    return ""
