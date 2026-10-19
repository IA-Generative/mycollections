"""L'intégration Open WebUI, figée : le manifeste du greffon et la signature de l'outil de
recherche. Le lot C remplace `search_collection` par `rechercher` : il change ce test dans sa PR."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]  # myrag/


def test_manifeste():
    yaml = pytest.importorskip("yaml", reason="pyyaml vient avec l'extra generation")
    m = yaml.safe_load((RACINE / "owui-plugin.yaml").read_text(encoding="utf-8"))
    outil = m["tools"]["entries"][0]
    assert outil["id"] == "myrag" and outil["source_file"] == "owui/tool_myrag.py"
    assert outil["methods"] == ["search_collection", "view_article", "explore_graph", "browse_collection"]
    assert m["filters"]["entries"][0]["id"] == "myrag-collection-filter"


def test_signature_de_search_collection():
    # Le module importe `requests`, absent des dépendances : on le lit, on ne l'importe pas.
    arbre = ast.parse((RACINE / "owui" / "tool_myrag.py").read_text(encoding="utf-8"))
    fonctions = {n.name: n for n in ast.walk(arbre) if isinstance(n, ast.AsyncFunctionDef)}
    assert [a.arg for a in fonctions["search_collection"].args.args] == ["self", "question", "collection", "__user__"]
