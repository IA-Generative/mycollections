"""Génération de paires question/réponse par persona, avec ragas (docs/generation.md).

Rien ici n'importe ragas : la bibliothèque est un extra (`uv sync --extra generation`) et le
reste du service doit démarrer sans elle. Les modules `modele` et `moteur` l'importent, et ne sont
chargés qu'au moment d'une génération.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

# ragas envoie des statistiques d'usage à son éditeur sauf avis contraire : aucune donnée ne doit
# sortir du ministère. Posé avant tout import de ragas, quel que soit le chemin qui y mène.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("TQDM_DISABLE", "1")

from app.config import settings  # noqa: E402


class GenerationIndisponible(RuntimeError):
    """La génération ne peut pas tourner ici : bibliothèque absente ou configuration incomplète."""


#: La passerelle dédiée, en deux variables. Posées ensemble, elles servent la génération ;
#: vides ensemble, c'est le repli OpenRAG (`fournisseur`) ; jamais une seule des deux
#: (`manques` la refuse). Le modèle de rédaction n'en fait pas partie : vide, la requête part
#: sans nom de modèle (`"model": ""`) et le serveur en aval choisit le sien — le mode direct
#: d'OpenRAG (aucun retriever) s'obtient exactement ainsi.
_REQUIS = (
    ("generation_llm_url", "MYCOLLECTIONS_GENERATION_LLM_URL"),
    ("generation_llm_cle", "MYCOLLECTIONS_GENERATION_LLM_CLE"),
)


@dataclass(frozen=True)
class Fournisseur:
    """Le serveur de rédaction : son adresse, sa clef, et s'il s'agit du repli OpenRAG."""

    url: str
    cle: str
    repli: bool


def fournisseur() -> Fournisseur:
    """Où joindre le modèle de rédaction.

    La passerelle dédiée (`MYCOLLECTIONS_GENERATION_LLM_URL` + `..._CLE`) quand elles sont
    posées ; sinon le `/v1` OpenAI-compatible d'OpenRAG, avec le jeton du service — sans nom
    de modèle, c'est son mode direct, sans retriever. Le repli emprunte le jeton d'OpenRAG :
    son quota de passerelle est partagé avec l'assistant, c'est le repli des essais, pas de
    la production (docs/generation.md, « Limites connues »).
    """
    url = str(settings.generation_llm_url or "").strip()
    if url or str(settings.generation_llm_cle or "").strip():
        return Fournisseur(url, str(settings.generation_llm_cle), repli=False)
    return Fournisseur(settings.openrag_url.rstrip("/") + "/v1", settings.openrag_admin_token, repli=True)


def disponible() -> bool:
    """ragas est-il installé ? (Sans l'importer : l'import coûte trois secondes et 200 Mo.)"""
    return importlib.util.find_spec("ragas") is not None


def manques() -> list[str]:
    """Les variables vides parmi celles qu'exige la génération : la passerelle dédiée exige
    URL **et** clef, vides ensemble c'est le repli OpenRAG — jamais une seule des deux, sans
    quoi le jeton d'OpenRAG partirait vers une autre adresse que la sienne."""
    posees = {var for champ, var in _REQUIS if str(getattr(settings, champ, "") or "").strip()}
    return [var for _, var in _REQUIS if var not in posees] if len(posees) == 1 else []


def prete() -> bool:
    return disponible() and not manques()


def exiger_prete() -> None:
    if not disponible():
        raise GenerationIndisponible("La génération de questions n'est pas installée sur ce service (extra « generation »).")
    vides = manques()
    if vides:
        raise GenerationIndisponible("La génération de questions n'est pas configurée : " + ", ".join(vides) + " manquante(s).")
