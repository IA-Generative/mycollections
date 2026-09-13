"""« Soyez acteurs vous-mêmes » — cinq pages Markdown servies à l'écran, et indexées
comme une collection interrogeable (amorce `guide`, ouverte aux propositions)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/guide", tags=["Guide"])
DOSSIER = Path(__file__).resolve().parent.parent / "guide"


def pages() -> list[dict]:
    resultat = []
    for chemin in sorted(DOSSIER.glob("*.md")):
        texte = chemin.read_text(encoding="utf-8")
        titre = next((l[2:].strip() for l in texte.splitlines() if l.startswith("# ")), chemin.stem)
        slug = re.sub(r"^\d+-", "", chemin.stem)
        resultat.append({"slug": slug, "titre": titre, "ordre": len(resultat) + 1, "fichier": chemin.name, "markdown": texte})
    return resultat


@router.get("")
async def lister():
    return {"titre": "Soyez acteurs vous-mêmes",
            "pages": [{k: v for k, v in p.items() if k != "markdown"} for p in pages()]}


@router.get("/{slug}")
async def lire(slug: str):
    for p in pages():
        if p["slug"] == slug:
            return p
    raise HTTPException(status_code=404, detail="Page du guide introuvable")
