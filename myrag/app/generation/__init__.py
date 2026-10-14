"""Génération de paires question/réponse par persona, avec ragas (docs/generation.md).

Rien ici n'importe ragas : la bibliothèque est un extra (`uv sync --extra generation`) et le
reste du service doit démarrer sans elle. Les modules `modele` et `moteur` l'importent, et ne sont
chargés qu'au moment d'une génération.
"""

from __future__ import annotations

import importlib.util
import os

# ragas envoie des statistiques d'usage à son éditeur sauf avis contraire : aucune donnée ne doit
# sortir du ministère. Posé avant tout import de ragas, quel que soit le chemin qui y mène.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("TQDM_DISABLE", "1")

from app.config import settings  # noqa: E402


class GenerationIndisponible(RuntimeError):
    """La génération ne peut pas tourner ici : bibliothèque absente ou configuration incomplète."""


#: Ce qu'il faut poser pour générer, dans l'ordre où on le dit.
_REQUIS = (
    ("generation_llm_url", "MYCOLLECTIONS_GENERATION_LLM_URL"),
    ("generation_llm_cle", "MYCOLLECTIONS_GENERATION_LLM_CLE"),
    ("generation_llm_modele", "MYCOLLECTIONS_GENERATION_LLM_MODELE"),
)


def disponible() -> bool:
    """ragas est-il installé ? (Sans l'importer : l'import coûte trois secondes et 200 Mo.)"""
    return importlib.util.find_spec("ragas") is not None


def manques() -> list[str]:
    """Les variables de configuration vides parmi celles qu'exige la génération."""
    return [var for champ, var in _REQUIS if not str(getattr(settings, champ, "") or "").strip()]


def prete() -> bool:
    return disponible() and not manques()


def exiger_prete() -> None:
    if not disponible():
        raise GenerationIndisponible(
            "La génération de questions n'est pas installée sur ce service (extra « generation »).")
    vides = manques()
    if vides:
        raise GenerationIndisponible(
            "La génération de questions n'est pas configurée : " + ", ".join(vides) + " manquante(s).")
