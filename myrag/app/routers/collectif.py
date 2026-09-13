"""Le circuit collaboratif d'une collection : état, grille, propositions,
signalements, journal, abonnement. Troisième routeur sous /api/collections."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.db import CIBLES_PROPOSITION, ETATS_SIGNALEMENT, MOTIFS_SIGNALEMENT
from app.routers._collectif_commun import (
    Identite, capacite, collection_lisible, date_avant, exiger_garant, identite, limite,
)
from app.services import collectif_store as store
from app.services.etats import RefusTransition

router = APIRouter(prefix="/api/collections", tags=["Collectif"])


class EtatEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cible: str
    forcer: bool = False
    motif: str = ""


class GrilleEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_licence: str | None = None
    donnees_perso: str | None = None
    fraicheur: str | None = None
    couverture: dict | None = None


class PropositionEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cible_type: str
    cible_ref: str = ""
    avant: str = ""
    apres: str
    justification: str
    source: str | None = None

    @field_validator("cible_type")
    @classmethod
    def _cible(cls, v):
        if v not in CIBLES_PROPOSITION:
            raise ValueError(f"La cible est l'une de : {', '.join(CIBLES_PROPOSITION)}")
        return v

    @field_validator("apres", "justification")
    @classmethod
    def _non_vide(cls, v):
        if not v or not v.strip():
            raise ValueError("Ce champ est obligatoire : l'après et la justification")
        return v.strip()

    @field_validator("source")
    @classmethod
    def _source(cls, v):
        return (v or "").strip() or None


class RefusEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motif: str

    @field_validator("motif")
    @classmethod
    def _motif(cls, v):
        if not v or not v.strip():
            raise ValueError("Un refus est toujours motivé")
        return v.strip()


class SignalementEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motif: str
    texte: str
    fichier_id: int | None = None

    @field_validator("motif")
    @classmethod
    def _motif(cls, v):
        if v not in MOTIFS_SIGNALEMENT:
            raise ValueError(f"Le motif est l'un de : {', '.join(MOTIFS_SIGNALEMENT)}")
        return v

    @field_validator("texte")
    @classmethod
    def _texte(cls, v):
        if not v or not v.strip():
            raise ValueError("Dites ce qui ne va pas")
        return v.strip()


class TraitementEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    etat: str

    @field_validator("etat")
    @classmethod
    def _etat(cls, v):
        if v not in ETATS_SIGNALEMENT or v == "ouvert":
            raise ValueError("Un signalement se traite en « pris_en_compte » ou « clos »")
        return v


# ─── État ─────────────────────────────────────────────────────────────────────────

@router.get("/{name}/etat")
async def lire_etat(f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return await store.lire_etat(f["name"], moi.hash, moi.superadmin)


@router.post("/{name}/etat")
async def changer_etat(entree: EtatEntree, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    exiger_garant(f, moi)
    if entree.forcer and not moi.superadmin:
        raise HTTPException(status_code=403, detail="Forcer le cycle est réservé à l'administration")
    try:
        return await store.changer_etat(f["name"], entree.cible, moi.hash, forcer=entree.forcer, motif=entree.motif.strip())
    except RefusTransition as e:
        raise HTTPException(status_code=e.code, detail=e.motif)


# ─── Grille ───────────────────────────────────────────────────────────────────────

@router.get("/{name}/grille")
async def lire_grille(f: dict = Depends(collection_lisible)):
    return {"collection": f["name"], "grille": await store.lire_grille(f["name"])}


@router.put("/{name}/grille")
async def maj_grille(entree: GrilleEntree, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    exiger_garant(f, moi)
    champs = entree.model_dump(exclude_none=True)
    if not champs:
        raise HTTPException(status_code=422, detail="Rien à mettre à jour")
    return {"collection": f["name"], "grille": await store.maj_grille(f["name"], champs, moi.hash)}


@router.post("/{name}/grille/relire")
async def relire(f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return {"collection": f["name"], "grille": await store.relire(f["name"], moi.hash)}


# ─── Propositions ─────────────────────────────────────────────────────────────────

@router.get("/{name}/propositions")
async def lister_propositions(f: dict = Depends(collection_lisible), etat: str | None = Query(None)):
    return {"collection": f["name"], "propositions": await store.lister_propositions(f["name"], etat)}


@router.post("/{name}/propositions", status_code=201)
async def proposer(entree: PropositionEntree, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return {"proposition": await store.creer_proposition(f["name"], entree.model_dump(), moi.hash)}


@router.get("/{name}/propositions/{ident}")
async def lire_proposition(ident: str, f: dict = Depends(collection_lisible)):
    try:
        return await store.lire_proposition(f["name"], ident)
    except store.Introuvable:
        raise HTTPException(status_code=404, detail="Proposition introuvable")


async def _decider(f, moi, ident, decision, motif):
    exiger_garant(f, moi)
    try:
        return {"proposition": await store.decider_proposition(f["name"], ident, decision, motif, moi.hash)}
    except store.Introuvable:
        raise HTTPException(status_code=404, detail="Proposition introuvable")
    except store.Conflit as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{name}/propositions/{ident}/publier")
async def publier_proposition(ident: str, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return await _decider(f, moi, ident, "publiee", None)


@router.post("/{name}/propositions/{ident}/refuser")
async def refuser_proposition(ident: str, entree: RefusEntree, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return await _decider(f, moi, ident, "refusee", entree.motif)


# ─── Signalements ─────────────────────────────────────────────────────────────────

@router.get("/{name}/signalements")
async def lister_signalements(f: dict = Depends(collection_lisible), etat: str | None = Query(None)):
    return {"collection": f["name"], "signalements": await store.lister_signalements(f["name"], etat)}


@router.post("/{name}/signalements", status_code=201, dependencies=[Depends(capacite("signalements"))])
async def signaler(entree: SignalementEntree, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return {"signalement": await store.creer_signalement(f["name"], entree.model_dump(), moi.hash)}


@router.post("/{name}/signalements/{ident}/traiter")
async def traiter_signalement(ident: str, entree: TraitementEntree, f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    exiger_garant(f, moi)
    try:
        return {"signalement": await store.traiter_signalement(f["name"], ident, entree.etat, moi.hash)}
    except store.Introuvable:
        raise HTTPException(status_code=404, detail="Signalement introuvable")


# ─── Journal et abonnement ────────────────────────────────────────────────────────

@router.get("/{name}/journal")
async def journal(f: dict = Depends(collection_lisible), limite_: int = Depends(limite),
                  avant: datetime | None = Depends(date_avant)):
    return await store.journal_de("collection", f["name"], limite_, avant)


@router.post("/{name}/abonner")
async def abonner(f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return {"abonne": await store.abonner("collection", f["name"], moi.hash, True)}


@router.delete("/{name}/abonner")
async def desabonner(f: dict = Depends(collection_lisible), moi: Identite = Depends(identite)):
    return {"abonne": await store.abonner("collection", f["name"], moi.hash, False)}
