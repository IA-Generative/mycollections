"""Le jeu de questions de référence d'une collection, et sa mesure (docs/qualite.md).

`QuestionFiche` couvre toutes les provenances (`origine`) : générée par persona (ragas),
importée, saisie, tirée d'un avis ou d'une amorce. Les dates sont servies en ISO 8601,
comme avant.
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.db import Mesure, MesureResultat, PaireQA


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _iso_vide(v: datetime | None) -> str:
    return v.isoformat() if v else ""


class QuestionFiche(BaseModel):
    """Une question du jeu de référence, d'où qu'elle vienne (docs/qualite.md)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str | None
    origine: str
    feedback_id: int | None
    must_cite: list[str]
    tags: list[str]
    hors_sujet: bool
    fiable: bool
    dernier_verdict: str | None
    derniere_mesure_le: str | None
    derniere_mesure_id: str | None
    modifie_le: str | None
    servie_fois: int
    collection: str
    rang: int
    question: str
    reponse: str
    contextes: list[dict]
    persona: str
    synthetiseur: str
    style: str
    longueur: str
    relecture: str
    commentaire: str
    relu_le: str | None
    cree_le: str

    @classmethod
    def depuis(cls, q: PaireQA) -> QuestionFiche:
        return cls(
            id=q.id,
            run_id=q.run_id,
            origine=q.origine,
            feedback_id=q.feedback_id,
            must_cite=json.loads(q.must_cite_json or "[]"),
            tags=json.loads(q.tags_json or "[]"),
            hors_sujet=bool(q.hors_sujet),
            fiable=bool(q.fiable),
            dernier_verdict=q.dernier_verdict,
            derniere_mesure_le=_iso(q.derniere_mesure_le),
            derniere_mesure_id=q.derniere_mesure_id,
            modifie_le=_iso(q.modifie_le),
            servie_fois=q.servie_fois or 0,
            collection=q.collection_name,
            rang=q.rang,
            question=q.question,
            reponse=q.reponse,
            contextes=json.loads(q.contextes_json or "[]"),
            persona=q.persona_nom,
            synthetiseur=q.synthetiseur,
            style=q.style,
            longueur=q.longueur,
            relecture=q.relecture,
            commentaire=q.commentaire,
            relu_le=_iso(q.relu_le),
            cree_le=_iso_vide(q.cree_le),
        )


class PageQuestions(BaseModel):
    """Une page du jeu de questions, et la suite s'il y en a une."""

    model_config = ConfigDict(extra="forbid")

    total: int
    page: int
    pages: int
    par_page: int
    questions: list[QuestionFiche]


class ComptesQuestions(BaseModel):
    """Les comptes du jeu de questions : total, par origine, par relecture, par verdict."""

    model_config = ConfigDict(extra="forbid")

    total: int
    par_origine: dict[str, int]
    par_relecture: dict[str, int]
    par_verdict: dict[str, int]
    fiables: int
    hors_sujet: int


class BilanImport(BaseModel):
    """Le bilan d'un import de questions : créées, doublons, ignorées."""

    model_config = ConfigDict(extra="forbid")

    crees: int
    doublons: int
    ignores: int


class MesureFiche(BaseModel):
    """Une mesure de la qualité : chaque question posée, comparée, et la synthèse."""

    model_config = ConfigDict(extra="forbid")

    id: str
    collection: str
    etat: str
    phase: str
    actif: bool
    methode: str
    modele: str
    filtre: dict
    nb_questions: int
    nb_traitees: int
    verdicts: dict[str, int]
    score: float | None
    compteurs: dict[str, int]
    duree_s: float | None
    erreur: str | None
    cree_le: str | None
    demarre_le: str | None
    termine_le: str | None

    @classmethod
    def depuis(cls, m: Mesure) -> MesureFiche:
        return cls(
            id=m.id,
            collection=m.collection_name,
            etat=m.etat,
            phase=m.phase,
            actif=m.etat in ("en_attente", "en_cours"),
            methode=m.methode,
            modele=m.modele,
            filtre=json.loads(m.filtre_json or "{}"),
            nb_questions=m.nb_questions,
            nb_traitees=m.nb_traitees,
            verdicts={k[3:]: getattr(m, k) for k in Mesure.VERDICTS},
            score=m.score,
            compteurs={k: getattr(m, k) for k in Mesure.COMPTEURS},
            duree_s=m.duree_s,
            erreur=m.erreur,
            cree_le=_iso(m.cree_le),
            demarre_le=_iso(m.demarre_le),
            termine_le=_iso(m.termine_le),
        )


class ResultatFiche(BaseModel):
    """Le résultat d'une question dans une mesure : l'instantané gardé, et le verdict."""

    model_config = ConfigDict(extra="forbid")

    id: str
    mesure_id: str
    question_id: str | None
    question: str
    reponse_reference: str
    hors_sujet: bool
    persona: str
    origine: str
    reponse_obtenue: str
    sources: list[dict]
    repli: str
    verdict: str
    justification: str
    score: float | None
    methode: str
    duree_s: float | None

    @classmethod
    def depuis(cls, x: MesureResultat) -> ResultatFiche:
        return cls(
            id=x.id,
            mesure_id=x.mesure_id,
            question_id=x.question_id,
            question=x.question_texte,
            reponse_reference=x.reponse_reference,
            hors_sujet=bool(x.hors_sujet),
            persona=x.persona_nom,
            origine=x.origine,
            reponse_obtenue=x.reponse_obtenue,
            sources=json.loads(x.sources_json or "[]"),
            repli=x.repli,
            verdict=x.verdict,
            justification=x.justification,
            score=x.score,
            methode=x.methode,
            duree_s=x.duree_s,
        )


class ResultatVolet(ResultatFiche):
    """Le résultat servi dans le volet d'une question : l'instant de la mesure en plus."""

    mesure_le: str | None


class PageResultats(BaseModel):
    """Une page des résultats d'une mesure, et la suite s'il y en a une."""

    model_config = ConfigDict(extra="forbid")

    total: int
    page: int
    pages: int
    par_page: int
    resultats: list[ResultatFiche]


class TendanceFiche(BaseModel):
    """Un point de la courbe de qualité : une mesure terminée, résumée."""

    model_config = ConfigDict(extra="forbid")

    id: str
    cree_le: str
    score: float | None
    nb_questions: int
    methode: str
