"""Ce que la barre commune (le bus de la bêta) demande à Mes collections POUR un
testeur, depuis n'importe quelle application : déposer une demande, la soutenir, lire
ce qu'il suit, signaler un document obsolète avec une nouvelle version.

Le bus est une machine : elle s'authentifie par `X-Bus-Secret` (temps constant), pas
par un jeton d'utilisateur — et elle transmet l'identité du visiteur en clair, comme
elle la reçoit, pour que le condensé calculé ICI soit le même que dans la cloche.
Secret absent ⇒ 503 : on refuse de servir plutôt que d'accepter sans vérifier.
"""

from __future__ import annotations

import base64
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator

from app.config import settings
from app.models.db import ROLES_SOUTIEN
from app.routers._collectif_commun import capacite
from app.routers.demandes import DemandeEntree
from app.services import capacites, doublons
from app.services import collectif_store as store
from app.services.pseudo import SelAbsent, condenser

router = APIRouter(prefix="/api/bus", tags=["Bus"])
VERSION_MAX = 5 * 1024 * 1024


async def admission(x_bus_secret: str = Header(default="")) -> None:
    if not settings.bus_secret:
        raise HTTPException(status_code=503, detail="Le bus n'est pas configuré (secret absent)")
    if not hmac.compare_digest(x_bus_secret.encode("utf-8"), settings.bus_secret.encode("utf-8")):
        raise HTTPException(status_code=401, detail="authentification refusée")


def _hash(visiteur: str | None) -> str:
    v = (visiteur or "").strip()
    if not v or len(v) > 200:
        raise HTTPException(status_code=400, detail="identifiant de visite absent")
    try:
        return condenser(v)
    except SelAbsent:
        raise HTTPException(status_code=503, detail="Le service n'est pas configuré pour le collectif (sel absent)")


class BusDemande(DemandeEntree):
    visiteur: str
    app: str | None = None


class BusSoutien(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visiteur: str
    role: str = "soutien"

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ROLES_SOUTIEN:
            raise ValueError("rôle inconnu")
        return v


class Version(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nom: str
    contenu_base64: str


class BusSignalement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visiteur: str
    collection: str
    texte: str
    document: str = ""
    motif: str = "obsolete"
    version: Version | None = None
    app: str | None = None

    @field_validator("texte")
    @classmethod
    def _texte(cls, v):
        if not v or not v.strip():
            raise ValueError("Dites ce qui ne va pas")
        return v.strip()

    @field_validator("motif")
    @classmethod
    def _motif(cls, v):
        if v not in ("obsolete", "erreur", "manquant"):
            raise ValueError("motif inconnu")
        return v


@router.get("/demandes", dependencies=[Depends(admission), Depends(capacite("demandes"))])
async def demandes(visiteur: str = Query(...), q: str | None = Query(None)):
    h = _hash(visiteur)
    liste = await store.lister_demandes(h)
    if q and q.strip():
        liste = doublons.candidats(q.strip(), [d for d in liste if d["etat"] != "close"])
    return {"demandes": liste, "seuil_chantier": (await capacites.lire_async())["seuil_chantier"]}


@router.post("/demandes", status_code=201, dependencies=[Depends(admission), Depends(capacite("demandes"))])
async def deposer(entree: BusDemande):
    h = _hash(entree.visiteur)
    seuil = int((await capacites.lire_async())["seuil_chantier"])
    donnees = entree.model_dump(exclude={"visiteur", "app"})
    demande = await store.creer_demande(donnees, h, seuil)
    return {"demande": demande, "url": f"{settings.myrag_public_url.rstrip('/')}/demandes/{demande['id']}"}


@router.post("/demandes/{ident}/soutenir", dependencies=[Depends(admission), Depends(capacite("demandes"))])
async def soutenir(ident: str, entree: BusSoutien):
    h = _hash(entree.visiteur)
    try:
        return {"demande": await store.soutenir(ident, h, entree.role, None)}
    except store.Introuvable:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    except store.Conflit as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/suivi", dependencies=[Depends(admission), Depends(capacite("demandes"))])
async def suivi(visiteur: str = Query(...)):
    h = _hash(visiteur)
    r = await store.suivi_pour(h)
    r["seuil_chantier"] = (await capacites.lire_async())["seuil_chantier"]
    r["url"] = f"{settings.myrag_public_url.rstrip('/')}/demandes"
    return r


@router.get("/collections", dependencies=[Depends(admission)])
async def collections():
    return {"collections": await store.collections_publiees_a_tous()}


@router.post("/signalements", status_code=201, dependencies=[Depends(admission), Depends(capacite("signalements"))])
async def signaler(entree: BusSignalement):
    h = _hash(entree.visiteur)
    try:
        f = await store.fiche(entree.collection)
    except store.Introuvable:
        raise HTTPException(status_code=404, detail="Collection introuvable")
    if f["etat_collab"] != "publiee_tous" and f["scope"] != "public":
        # Sans les groupes du visiteur, on ne sait pas s'il peut la lire : on ne le dit pas.
        raise HTTPException(status_code=404, detail="Collection introuvable")
    texte = entree.texte if not entree.document else f"Document cité : {entree.document}\n{entree.texte}"
    signalement = await store.creer_signalement(entree.collection, {"motif": entree.motif, "texte": texte, "fichier_id": None}, h)
    proposition = None
    if entree.version:
        try:
            contenu = base64.b64decode(entree.version.contenu_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=422, detail="version illisible (base64 attendu)")
        if not contenu or len(contenu) > VERSION_MAX:
            raise HTTPException(status_code=413, detail="version vide ou trop lourde (5 Mio au plus)")
        proposition = await store.deposer_version(entree.collection, entree.document or entree.version.nom,
                                                  entree.version.nom, contenu, h, signalement["id"])
    return {"signalement": signalement, "proposition": proposition}
