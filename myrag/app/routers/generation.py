"""Générer des paires question/réponse par persona sur une collection (docs/generation.md).

Toutes les routes sont réservées à qui GÈRE la collection (créateur, groupe `<nom>-admin`,
administration) : 404 si on ne peut pas la lire, 403 si on la lit seulement. Service non
installé, ou passerelle posée à moitié (URL sans clef ou l'inverse) : 503, avec ce qui
manque ; sans passerelle du tout, repli sur le `/v1` d'OpenRAG (dit `via_openrag`).
"""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import generation
from app.auth import CurrentUser
from app.config import settings
from app.models.db import RELECTURES_PAIRE
from app.routers._droits import gerer_la_collection
from app.services import corpus
from app.services import generation_store as store
from app.services.collectif_store import Conflit, Introuvable, consigner
from app.services.openrag_client import OpenRAGClient

DISTRIBUTIONS = ("entites", "mots_cles")


async def exiger_generation() -> None:
    try:
        generation.exiger_prete()
    except generation.GenerationIndisponible as e:
        raise HTTPException(status_code=503, detail=str(e))


router = APIRouter(prefix="/api/collections/{collection}/generation", tags=["Generation"], dependencies=[Depends(exiger_generation)])


def _traduire(e: Exception):
    if isinstance(e, Introuvable):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, Conflit):
        raise HTTPException(status_code=409, detail=str(e))
    raise e


class PersonaEntree(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nom: str = Field(min_length=1, max_length=120)
    description_role: str = Field(min_length=1, max_length=2000)


class PersonaModification(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nom: str | None = Field(default=None, min_length=1, max_length=120)
    description_role: str | None = Field(default=None, min_length=1, max_length=2000)


class RunEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    personas: list[str] = Field(min_length=1, max_length=5)
    taille: int = Field(default=20, ge=1, le=100)
    distribution: dict[str, float] = Field(default_factory=lambda: {"entites": 1.0})

    @field_validator("personas")
    @classmethod
    def _uniques(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Un persona n'est choisi qu'une fois")
        return v

    @field_validator("distribution")
    @classmethod
    def _distribution(cls, v):
        if not v or any(k not in DISTRIBUTIONS for k in v) or any(p <= 0 for p in v.values()):
            raise ValueError(f"Distribution : clés parmi {', '.join(DISTRIBUTIONS)}, poids positifs")
        total = sum(v.values())
        return {k: round(p / total, 4) for k, p in v.items()}


class RelectureEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relecture: str
    commentaire: str | None = Field(default=None, max_length=2000)

    @field_validator("relecture")
    @classmethod
    def _domaine(cls, v):
        if v not in RELECTURES_PAIRE:
            raise ValueError(f"relecture parmi {', '.join(RELECTURES_PAIRE)}")
        return v


@router.get("")
async def etat(collection: str, user: CurrentUser = Depends(gerer_la_collection)):
    return {
        "collection": collection,
        "prete": True,
        "modele": settings.generation_llm_modele,
        "via_openrag": generation.fournisseur().repli,
        "morceaux_max": settings.generation_morceaux_max,
        "taille_max": 100,
        "personas": await store.lister_personas(collection),
        "run_actif": await store.run_actif(collection),
    }


# ─── Personas ─────────────────────────────────────────────────────────────────────


@router.get("/personas")
async def lister_personas(collection: str, user: CurrentUser = Depends(gerer_la_collection)):
    return {"personas": await store.lister_personas(collection)}


@router.post("/personas", status_code=201)
async def creer_persona(collection: str, corps: PersonaEntree, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        return {"persona": await store.creer_persona(collection, corps.nom, corps.description_role, user.sub)}
    except (Conflit, Introuvable) as e:
        _traduire(e)


class PropositionEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: int = Field(default=4, ge=1, le=6)


@router.post("/personas/propositions")
async def proposer_personas(collection: str, corps: PropositionEntree, user: CurrentUser = Depends(gerer_la_collection)):
    """Des personas proposés d'après les documents (un appel au modèle). Rien n'est enregistré."""
    from app.generation import suggestion
    from app.generation.resultats import message_sur

    existants = [p.nom for p in await store.lister_personas(collection)]
    try:
        return await suggestion.proposer(collection, corps.nombre, existants)
    except LookupError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # noqa: BLE001 — modèle injoignable, quota… : dit, jamais muet
        raise HTTPException(status_code=502, detail=message_sur(e))


@router.patch("/personas/{ident}")
async def modifier_persona(collection: str, ident: str, corps: PersonaModification, user: CurrentUser = Depends(gerer_la_collection)):
    champs = corps.model_dump(exclude_none=True)
    if not champs:
        raise HTTPException(status_code=422, detail="Rien à mettre à jour")
    try:
        return {"persona": await store.modifier_persona(collection, ident, champs)}
    except (Conflit, Introuvable) as e:
        _traduire(e)


@router.delete("/personas/{ident}")
async def supprimer_persona(collection: str, ident: str, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        await store.supprimer_persona(collection, ident)
    except (Conflit, Introuvable) as e:
        _traduire(e)
    return {"status": "deleted"}


# ─── Runs ─────────────────────────────────────────────────────────────────────────


@router.post("/runs", status_code=202)
async def lancer(collection: str, corps: RunEntree, user: CurrentUser = Depends(gerer_la_collection)):
    from app.generation import execution

    try:
        personas = await store.personas_par_ids(collection, corps.personas)
    except Introuvable as e:
        _traduire(e)
    try:
        fichiers = await corpus.fichiers_de(OpenRAGClient(), collection)
    except Exception:
        raise HTTPException(status_code=502, detail="Le corpus n'a pas pu être lu : OpenRAG ne répond pas.")
    if not fichiers:
        raise HTTPException(status_code=409, detail="Cette collection n'a encore aucun document.")
    try:
        run = await store.creer_run(collection, personas, corps.taille, corps.distribution, settings.generation_llm_modele, user.sub)
    except Conflit as e:
        _traduire(e)
    await consigner(
        "collection",
        collection,
        "generation.lancee",
        user.sub,
        collection_name=collection,
        detail={"run": run.id, "taille": corps.taille, "personas": [p.nom for p in personas]},
    )
    execution.lancer(run, collection, personas)
    return {"run": run}


@router.get("/runs")
async def lister_runs(collection: str, user: CurrentUser = Depends(gerer_la_collection)):
    return {"runs": await store.lister_runs(collection)}


@router.get("/runs/{ident}")
async def lire_run(collection: str, ident: str, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        return {"run": await store.lire_run(collection, ident)}
    except Introuvable as e:
        _traduire(e)


@router.delete("/runs/{ident}")
async def supprimer_run(collection: str, ident: str, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        await store.supprimer_run(collection, ident)
    except (Conflit, Introuvable) as e:
        _traduire(e)
    return {"status": "deleted"}


# ─── Paires ───────────────────────────────────────────────────────────────────────


@router.get("/runs/{ident}/paires")
async def lister_paires(
    collection: str,
    ident: str,
    persona: str | None = Query(None, max_length=120),
    relecture: str | None = Query(None, pattern="^(brut|valide|rejete)$"),
    page: int = Query(1, ge=1),
    par_page: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(gerer_la_collection),
):
    try:
        await store.lire_run(collection, ident)
    except Introuvable as e:
        _traduire(e)
    return await store.lister_paires(collection, ident, persona=persona, relecture=relecture, page=page, par_page=par_page)


@router.patch("/paires/{ident}")
async def relire_paire(collection: str, ident: str, corps: RelectureEntree, user: CurrentUser = Depends(gerer_la_collection)):
    try:
        return {"paire": await store.relire_paire(collection, ident, corps.relecture, corps.commentaire, user.sub)}
    except Introuvable as e:
        _traduire(e)


def _cellule(v) -> str:
    """Un tableur exécuterait une cellule qui commence par = + - @ : on la neutralise."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/runs/{ident}/export")
async def exporter(collection: str, ident: str, format: str = Query("json", pattern="^(json|csv)$"), user: CurrentUser = Depends(gerer_la_collection)):
    try:
        run = await store.lire_run(collection, ident)
    except Introuvable as e:
        _traduire(e)
    paires = await store.paires_pour_export(collection, ident)
    nom = f"{collection}-questions-{ident[:8]}.{format}"
    entete = {"Content-Disposition": f'attachment; filename="{nom}"'}
    if format == "json":
        # Le format de l'outillage d'évaluation (eval-rag, DatasetItem) : question, answer, context,
        # persona_name, query_style — plus de quoi retrouver les passages et la relecture.
        corps = {
            "metadata": {"collection": collection, "run": ident, "modele": run.modele, "cree_le": run.cree_le, "total_samples": len(paires)},
            "samples": [
                {
                    "question": p.question,
                    "answer": p.reponse,
                    "context": [c.get("texte", "") for c in p.contextes],
                    "persona_name": p.persona,
                    "query_style": p.style,
                    "metadata": {
                        "query_length": p.longueur,
                        "synthetiseur": p.synthetiseur,
                        "chunk_ids": [c.get("chunk_id") for c in p.contextes],
                        "file_ids": [c.get("file_id") for c in p.contextes],
                        "relecture": p.relecture,
                        "commentaire": p.commentaire,
                    },
                }
                for p in paires
            ],
        }
        return Response(json.dumps(corps, ensure_ascii=False, indent=2), media_type="application/json", headers=entete)
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";")
    w.writerow(["id", "persona", "question", "reponse", "style", "longueur", "relecture", "commentaire", "chunk_ids", "file_ids", "fichiers"])
    for p in paires:
        w.writerow(
            [
                _cellule(x)
                for x in (
                    p.id,
                    p.persona,
                    p.question,
                    p.reponse,
                    p.style,
                    p.longueur,
                    p.relecture,
                    p.commentaire,
                    " ".join(str(c.get("chunk_id") or "") for c in p.contextes),
                    " ".join(str(c.get("file_id") or "") for c in p.contextes),
                    " | ".join(str(c.get("fichier") or "") for c in p.contextes),
                )
            ]
        )
    return Response("﻿" + tampon.getvalue(), media_type="text/csv; charset=utf-8", headers=entete)
