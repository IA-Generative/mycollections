"""La génération de paires question/réponse par persona (docs/generation.md).

`QuestionFiche` vient du module qualite : une paire générée est une question du jeu
de référence, comme les autres origines.
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.db import Generation, Persona
from app.models.qualite import QuestionFiche


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _iso_vide(v: datetime | None) -> str:
    return v.isoformat() if v else ""


class PersonaFiche(BaseModel):
    """Qui interroge la collection, et dans quel contexte."""

    model_config = ConfigDict(extra="forbid")

    id: str
    collection: str
    nom: str
    description_role: str
    cree_le: str
    maj_le: str

    @classmethod
    def depuis(cls, p: Persona) -> PersonaFiche:
        return cls(
            id=p.id,
            collection=p.collection_name,
            nom=p.nom,
            description_role=p.description_role,
            cree_le=_iso_vide(p.cree_le),
            maj_le=_iso_vide(p.maj_le),
        )


class RunFiche(BaseModel):
    """Un run de génération : ce qui a été demandé, où il en est, ce qu'il a coûté."""

    model_config = ConfigDict(extra="forbid")

    id: str
    collection: str
    personas: list[dict]
    personas_auto: bool
    taille: int
    distribution: dict[str, float]
    modele: str
    etat: str
    phase: str
    actif: bool
    fichiers_collection: int
    morceaux_envoyes: int
    noeuds_avec_proprietes: int
    paires_obtenues: int
    paires_echouees: int
    compteurs: dict[str, int]
    duree_s: float | None
    erreur: str | None
    cree_le: str | None
    demarre_le: str | None
    termine_le: str | None

    @classmethod
    def depuis(cls, g: Generation) -> RunFiche:
        return cls(
            id=g.id,
            collection=g.collection_name,
            personas=json.loads(g.personas_json or "[]"),
            personas_auto=bool(g.personas_auto),
            taille=g.taille,
            distribution=json.loads(g.distribution_json or "{}"),
            modele=g.modele,
            etat=g.etat,
            phase=g.phase,
            actif=g.etat in ("en_attente", "en_cours"),
            fichiers_collection=g.fichiers_collection,
            morceaux_envoyes=g.morceaux_envoyes,
            noeuds_avec_proprietes=g.noeuds_avec_proprietes,
            paires_obtenues=g.paires_obtenues,
            paires_echouees=g.paires_echouees,
            compteurs={k: getattr(g, k) for k in Generation.COMPTEURS},
            duree_s=g.duree_s,
            erreur=g.erreur,
            cree_le=_iso(g.cree_le),
            demarre_le=_iso(g.demarre_le),
            termine_le=_iso(g.termine_le),
        )


class PagePaires(BaseModel):
    """Une page des paires générées par un run, et la suite s'il y en a une."""

    model_config = ConfigDict(extra="forbid")

    total: int
    page: int
    pages: int
    par_page: int
    paires: list[QuestionFiche]
