"""Piloter la qualité d'une collection : son jeu de questions de référence (docs/qualite.md).

Réservé à qui GÈRE la collection (404 si on ne peut pas la lire, 403 si on la lit seulement).
Ne dépend pas de ragas : saisir, importer, corriger et valider des questions fonctionne partout.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth import CurrentUser
from app.models.db import ORIGINES_QUESTION, RELECTURES_PAIRE
from app.routers._droits import gerer_la_collection
from app.services import export_questions
from app.services import questions_store as store
from app.services.collectif_store import Conflit, Introuvable, consigner

router = APIRouter(prefix="/api/collections/{collection}/qualite", tags=["Qualite"])


def _traduire(e: Exception):
    if isinstance(e, Introuvable):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, Conflit):
        raise HTTPException(status_code=409, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    raise e


class QuestionEntree(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=store.QUESTION_MAX)
    reponse: str = Field(default="", max_length=store.REPONSE_MAX)
    must_cite: list[str] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=30)
    hors_sujet: bool = False
    persona: str = Field(default="", max_length=120)
    relecture: str = Field(default="brut", pattern="^(brut|valide|rejete)$")


class QuestionModification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str | None = Field(default=None, max_length=store.QUESTION_MAX)
    reponse: str | None = Field(default=None, max_length=store.REPONSE_MAX)
    must_cite: list[str] | None = None
    tags: list[str] | None = None
    hors_sujet: bool | None = None
    fiable: bool | None = None
    relecture: str | None = Field(default=None, pattern="^(brut|valide|rejete)$")
    commentaire: str | None = Field(default=None, max_length=2000)
    persona: str | None = Field(default=None, max_length=120)


class ImportEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[dict] | None = None
    samples: list[dict] | None = None


class AvisEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reponse: str = Field(default="", max_length=store.REPONSE_MAX)


@router.get("/questions")
async def lister(
    collection: str,
    origine: str | None = Query(None, pattern="^(" + "|".join(ORIGINES_QUESTION) + ")$"),
    relecture: str | None = Query(None, pattern="^(" + "|".join(RELECTURES_PAIRE) + ")$"),
    verdict: str | None = Query(None, max_length=20),
    fiable: bool | None = None,
    hors_sujet: bool | None = None,
    persona: str | None = Query(None, max_length=120),
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    par_page: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(gerer_la_collection),
):
    page_ = await store.lister_questions(
        collection, origine=origine, relecture=relecture, verdict=verdict, fiable=fiable, hors_sujet=hors_sujet, persona=persona, texte=q, page=page, par_page=par_page
    )
    return {**page_, "comptes": await store.compter(collection)}


@router.post("/questions", status_code=201)
async def creer(collection: str, corps: QuestionEntree, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        return {"question": await store.creer_question(collection, corps.model_dump(), user.sub, origine="saisie")}
    except (Conflit, Introuvable, ValueError) as e:
        _traduire(e)


@router.post("/questions/import", status_code=201)
async def importer(collection: str, corps: ImportEntree, user: CurrentUser = Depends(gerer_la_collection)):
    items = corps.questions if corps.questions is not None else (corps.samples or [])
    if not items:
        raise HTTPException(status_code=422, detail="Le fichier ne contient aucune question (clé « questions » ou « samples »).")
    try:
        bilan = await store.importer_questions(collection, items, user.sub, origine="importee")
    except ValueError as e:
        _traduire(e)
    await consigner("collection", collection, "questions.importees", user.sub, collection_name=collection, detail=bilan)
    return bilan


@router.post("/questions/depuis-avis/{feedback_id}", status_code=201)
async def depuis_avis(collection: str, feedback_id: int, corps: AvisEntree, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        return {"question": await store.depuis_avis(collection, feedback_id, corps.reponse, user.sub)}
    except (Conflit, Introuvable, ValueError) as e:
        _traduire(e)


@router.get("/questions/export")
async def exporter(collection: str, format: str = Query("json", pattern="^(json|csv)$"), user: CurrentUser = Depends(gerer_la_collection)):
    questions = (await store.lister_questions(collection, par_page=200, page=1))["questions"]
    total = (await store.compter(collection))["total"]
    page = 2
    while len(questions) < total:
        questions += (await store.lister_questions(collection, par_page=200, page=page))["questions"]
        page += 1
    nom = f"{collection}-jeu-de-questions.{format}"
    entete = {"Content-Disposition": f'attachment; filename="{nom}"'}
    if format == "json":
        return Response(export_questions.vers_json(collection, questions), media_type="application/json", headers=entete)
    return Response(export_questions.vers_csv(questions), media_type="text/csv; charset=utf-8", headers=entete)


@router.get("/questions/{ident}")
async def lire(collection: str, ident: str, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        return {"question": await store.lire_question(collection, ident)}
    except Introuvable as e:
        _traduire(e)


@router.patch("/questions/{ident}")
async def modifier(collection: str, ident: str, corps: QuestionModification, user: CurrentUser = Depends(gerer_la_collection)):
    champs = corps.model_dump(exclude_unset=True)
    if not champs:
        raise HTTPException(status_code=422, detail="Rien à modifier")
    try:
        return {"question": await store.modifier_question(collection, ident, champs, user.sub)}
    except (Conflit, Introuvable, ValueError) as e:
        _traduire(e)


@router.delete("/questions/{ident}")
async def supprimer(collection: str, ident: str, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        await store.supprimer_question(collection, ident)
    except Introuvable as e:
        _traduire(e)
    return {"status": "deleted"}
