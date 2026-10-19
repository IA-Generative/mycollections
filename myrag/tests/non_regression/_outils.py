"""Outils des tests de non-régression : formes et fichiers figés.

Un fichier figé (`fixtures/<nom>.json`) se (ré)écrit explicitement, jamais par accident :

    MYCOLLECTIONS_NONREG_ENREGISTRER=1 uv run pytest tests/non_regression

puis le diff du fichier se relit dans la PR qui change le comportement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REP_FIXTURES = Path(__file__).parent / "fixtures"
VARIABLE = "MYCOLLECTIONS_NONREG_ENREGISTRER"


def forme(objet):
    """La structure d'une réponse sans ses valeurs : clés triées, types, premier élément des listes."""
    if isinstance(objet, dict):
        return {k: forme(v) for k, v in sorted(objet.items())}
    if isinstance(objet, list):
        return [forme(objet[0])] if objet else []
    if objet is None:
        return "null"
    if isinstance(objet, bool):
        return "bool"
    if isinstance(objet, int):
        return "int"
    if isinstance(objet, float):
        return "float"
    if isinstance(objet, str):
        return "str"
    return type(objet).__name__


def figer(nom: str, obtenu) -> None:
    """Compare `obtenu` au fichier figé `fixtures/<nom>.json` ; l'écrit si on l'a demandé."""
    chemin = REP_FIXTURES / f"{nom}.json"
    texte = json.dumps(obtenu, ensure_ascii=False, indent=2) + "\n"
    if os.environ.get(VARIABLE) == "1":
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")
        pytest.fail(f"{chemin.name} enregistré : relire le diff, puis relancer sans {VARIABLE}")
    assert chemin.exists(), f"pas de fichier figé {chemin.name} : lancer avec {VARIABLE}=1 pour l'enregistrer"
    attendu = json.loads(chemin.read_text(encoding="utf-8"))
    assert obtenu == attendu, f"le comportement figé dans {chemin.name} a changé ; si c'est voulu, ré-enregistrer avec {VARIABLE}=1 et relire le diff"
