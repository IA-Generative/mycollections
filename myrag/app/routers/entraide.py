"""Le réseau d'entraide (lot G du chantier des assistants de recherche) : appels à l'aide,
réponses, demandes du collectif lues en référence. Routeur déjà monté et gardé par le drapeau
`entraide` : le lot G le remplit sans toucher `main.py`. Module détachable : routes, tables
(`app/models/entraide.py`) et pages sous un seul préfixe, aucune dépendance entrante."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.entraide import ETATS_APPEL, TYPES_APPEL, TYPES_REDIGES
from app.routers._commun import Identite, capacite, identite
from app.services import entraide_store as store

router = APIRouter(prefix="/api/entraide", tags=["entraide"], dependencies=[Depends(capacite("entraide"))])


def _non_vide(v: str, message: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(message)
    return v.strip()


class AppelEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")  # ni état, ni auteur : le serveur décide

    type: str
    titre: str
    texte: str = ""

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v not in TYPES_REDIGES:
            raise ValueError(f"Le type d'appel est l'un de : {', '.join(TYPES_REDIGES)} (une donnée qui manque se demande sur /demandes)")
        return v

    @field_validator("titre")
    @classmethod
    def _titre(cls, v):
        return _non_vide(v, "Le titre est obligatoire")[:200]

    @field_validator("texte")
    @classmethod
    def _texte(cls, v):
        return (v or "").strip()[:5000]


class ReponseEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texte: str

    @field_validator("texte")
    @classmethod
    def _texte(cls, v):
        return _non_vide(v, "Écrivez votre réponse")[:5000]


class LienEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demande_id: str


def _404(e: Exception):
    return HTTPException(status_code=404, detail="Appel introuvable")


def _409(e: Exception):
    return HTTPException(status_code=409, detail=str(e))


async def _auteur_ou_admin(ident: str, moi: Identite, geste: str) -> None:
    if ident.startswith(store.PREFIXE_DEMANDE):
        raise HTTPException(status_code=409, detail="Cette demande du collectif se gère depuis sa page")
    try:
        # Un brouillon d'autrui reste introuvable : on ne confirme pas qu'il existe.
        fiche = await store.lire(ident, moi.hash)
    except store.Introuvable as e:
        raise _404(e)
    if not (fiche["est_mon_appel"] or moi.superadmin):
        raise HTTPException(status_code=403, detail=f"{geste} revient à la personne qui a lancé l'appel")
    if geste == "Publier" and not fiche["est_mon_appel"]:
        raise HTTPException(status_code=403, detail="Publier revient à la personne qui a lancé l'appel")


@router.get("")
async def lister(
    moi: Identite = Depends(identite),
    type: str | None = Query(None),
    etat: str | None = Query(None),
    q: str | None = Query(None),
):
    if type and type not in TYPES_APPEL:
        raise HTTPException(status_code=422, detail=f"Le type est l'un de : {', '.join(TYPES_APPEL)}")
    if etat and etat not in ETATS_APPEL:
        raise HTTPException(status_code=422, detail=f"L'état est l'un de : {', '.join(ETATS_APPEL)}")
    return {"appels": await store.lister(moi.hash, type_=type, etat=etat, q=q)}


@router.post("/appels", status_code=201)
async def creer(entree: AppelEntree, moi: Identite = Depends(identite)):
    """Crée un brouillon : rien n'est visible des autres avant `publier`."""
    return {"appel": await store.creer(entree.model_dump(), moi.hash)}


@router.get("/appels/{ident}")
async def lire(ident: str, moi: Identite = Depends(identite)):
    try:
        return {"appel": await store.lire(ident, moi.hash)}
    except store.Introuvable as e:
        raise _404(e)


@router.post("/appels/{ident}/publier")
async def publier(ident: str, moi: Identite = Depends(identite)):
    await _auteur_ou_admin(ident, moi, "Publier")
    try:
        return {"appel": await store.publier(ident, moi.hash)}
    except store.Conflit as e:
        raise _409(e)


@router.post("/appels/{ident}/clore")
async def clore(ident: str, moi: Identite = Depends(identite)):
    await _auteur_ou_admin(ident, moi, "Clore")
    try:
        return {"appel": await store.clore(ident, moi.hash)}
    except store.Conflit as e:
        raise _409(e)


@router.post("/appels/{ident}/reponses", status_code=201)
async def repondre(ident: str, entree: ReponseEntree, moi: Identite = Depends(identite)):
    if ident.startswith(store.PREFIXE_DEMANDE):
        raise HTTPException(status_code=409, detail="Pour une donnée qui manque, dites « moi aussi » depuis la demande")
    try:
        return {"reponse": await store.repondre(ident, entree.texte, moi.hash)}
    except store.Introuvable as e:
        raise _404(e)
    except store.Conflit as e:
        raise _409(e)


@router.post("/appels/{ident}/liens")
async def lier(ident: str, entree: LienEntree, moi: Identite = Depends(identite)):
    """Rattache l'appel à une demande existante, par référence."""
    await _auteur_ou_admin(ident, moi, "Lier")
    try:
        return {"demandes_liees": await store.lier_demande(ident, entree.demande_id)}
    except store.Introuvable:
        raise HTTPException(status_code=404, detail="Demande introuvable")
