"""Le catalogue des amorces : ce qu'on constitue depuis l'open data avant d'ouvrir
la section collaborative. Un fichier versionné, sans secret ; les clés d'API vivent
dans l'environnement (lot 5)."""

from __future__ import annotations

import json
from pathlib import Path

_CHEMIN = Path(__file__).parent / "catalogue.json"


def charger_catalogue() -> list[dict]:
    with _CHEMIN.open(encoding="utf-8") as f:
        entrees = json.load(f)["amorces"]
    for e in entrees:
        e.setdefault("collection", f"amorce-{e['id']}")
        e.setdefault("grille", {})
    return entrees


def entree(identifiant: str) -> dict | None:
    return next((e for e in charger_catalogue() if e["id"] == identifiant), None)
