"""Les rubriques du catalogue : tout le monde les lit, un superadmin les règle.

Catégories ET classement des collections se changent à chaud, sans redéploiement.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers._collectif_commun import Identite, exiger_superadmin, identite
from app.services import categorie_store as store
from app.services.nommage import cle_valide

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CreerCategorie(BaseModel):
    cle: str = Field(min_length=2, max_length=64)
    libelle: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)


class ModifierCategorie(BaseModel):
    libelle: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class Ordre(BaseModel):
    cles: list[str]


class Affectations(BaseModel):
    #: {nom de collection: clé de catégorie, ou null pour « Non classées »}
    affectations: dict[str, str | None]


@router.get("")
async def lister(moi: Identite = Depends(identite)):
    return {"categories": await store.lister()}


@router.post("", status_code=201)
async def creer(req: CreerCategorie, moi: Identite = Depends(exiger_superadmin)):
    cle = req.cle.strip().lower()
    if not cle_valide(cle):
        raise HTTPException(status_code=422, detail="Clé invalide : minuscules, chiffres et tirets (ex. droit-etrangers)")
    try:
        return {"categorie": await store.creer(cle, req.libelle.strip(), req.description.strip())}
    except store.DejaLa:
        raise HTTPException(status_code=409, detail=f"La catégorie « {cle} » existe déjà")


# Avant /{cle} : « ordre » et « affectations » ne sont pas des clés de catégorie.
@router.put("/ordre")
async def ordonner(req: Ordre, moi: Identite = Depends(exiger_superadmin)):
    try:
        return {"categories": await store.ordonner(req.cles)}
    except store.Introuvable as e:
        raise HTTPException(status_code=404, detail=f"Catégorie inconnue : {e}")


@router.put("/affectations")
async def affecter(req: Affectations, moi: Identite = Depends(exiger_superadmin)):
    try:
        bilan = await store.affecter(req.affectations, moi.hash)
    except store.Introuvable as e:
        raise HTTPException(status_code=404, detail=str(e))
    # Le classement est l'étiquette des fiches de l'assistant : on le DIT, on ne le rejoue pas
    # d'office (le socle peut être lent, et l'administration classe souvent en plusieurs fois).
    return {**bilan, "categories": await store.lister(), "resync_conseillee": bool(bilan["changees"])}


@router.patch("/{cle}")
async def modifier(cle: str, req: ModifierCategorie, moi: Identite = Depends(exiger_superadmin)):
    try:
        return {"categorie": await store.modifier(cle, libelle=req.libelle, description=req.description),
                "resync_conseillee": req.libelle is not None}
    except store.Introuvable:
        raise HTTPException(status_code=404, detail=f"Catégorie inconnue : {cle}")


@router.delete("/{cle}")
async def supprimer(cle: str, moi: Identite = Depends(exiger_superadmin)):
    try:
        declassees = await store.supprimer(cle)
        return {"supprimee": cle, "collections_declassees": declassees, "resync_conseillee": declassees > 0}
    except store.Introuvable:
        raise HTTPException(status_code=404, detail=f"Catégorie inconnue : {cle}")
