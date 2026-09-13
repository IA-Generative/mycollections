"""Le guide « Soyez acteurs vous-mêmes » comme collection : une page = un document."""

from __future__ import annotations

from app.routers.guide import pages
from app.services.amorces.ingestion import Document


def documents_depuis(liste: list[dict]) -> tuple[list[Document], dict]:
    docs = [Document(nom=p["fichier"], texte=p["markdown"], metadonnees={"slug": p["slug"]}) for p in liste]
    return docs, {"pages": [p["titre"] for p in liste], "documents": len(docs)}


async def importer(collection: str, entree: dict) -> dict:
    from app.services.amorces.ingestion import ingerer
    docs, couverture = documents_depuis(pages())
    bilan = await ingerer(collection, docs, strategie="section")
    return {**bilan, "couverture": couverture, "lignes_importees": len(docs)}
