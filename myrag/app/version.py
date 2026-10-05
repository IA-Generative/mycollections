"""Convention ADR-0004 MirAI next, format Dockerflow : /app/version.json servi sur /__version__."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

VERSION_JSON = Path("/app/version.json")
DEV = {"source": "", "version": "dev", "commit": "", "build": "", "code_date": "", "changes": [], "history": []}

router = APIRouter()


def lire() -> dict:
    """Le journal que l'image porte. Hors image le fichier manque : « dev », jamais une erreur."""
    try:
        return json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEV)


@router.get("/__version__", include_in_schema=False)
def version_json() -> dict:
    return lire()
