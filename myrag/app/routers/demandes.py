"""Les demandes de jeux de données : un usage, une fréquence, comment on fait
aujourd'hui — jamais un score. Le passage en chantier se décide ici, côté serveur."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.db import FREQUENCES_DEMANDE, ROLES_SOUTIEN
from app.routers._collectif_commun import Identite, capacite, date_avant, identite, limite
from app.services import capacites, doublons
from app.services import collectif_store as store

router = APIRouter(prefix="/api/demandes", tags=["Demandes"], dependencies=[Depends(capacite("demandes"))])

MESSAGE_ACCES_ACTUEL = (
    "Comment vous procurez-vous cette donnée aujourd'hui ? Sans cette information, il nous "
    "est pratiquement impossible de constituer un nouveau jeu de données : c'est elle qui en "
    "révèle la source, le format et les conditions d'accès."
)
MESSAGE_RECONTACT = "Acceptez-vous d'être recontacté·e pour soutenir cette initiative ? La réponse est attendue."


def _non_vide(v: str, message: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(message)
    return v.strip()


class DemandeEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")  # ni score, ni note, ni priorité, ni état

    titre: str
    usage: str
    frequence: str
    service: str = ""
    acces_actuel: str
    recontact: bool
    contact: str | None = None
    amorce_id: str | None = None

    @field_validator("titre")
    @classmethod
    def _titre(cls, v):
        return _non_vide(v, "Le titre est obligatoire")[:200]

    @field_validator("usage")
    @classmethod
    def _usage(cls, v):
        return _non_vide(v, "Dites à quoi servira ce jeu de données")

    @field_validator("acces_actuel")
    @classmethod
    def _acces(cls, v):
        return _non_vide(v, MESSAGE_ACCES_ACTUEL)

    @field_validator("frequence")
    @classmethod
    def _frequence(cls, v):
        if v not in FREQUENCES_DEMANDE:
            raise ValueError(f"La fréquence est l'une de : {', '.join(FREQUENCES_DEMANDE)}")
        return v

    @model_validator(mode="after")
    def _contact_consenti(self):
        if self.contact and not self.recontact:
            raise ValueError("Un courriel n'est enregistré qu'avec votre accord d'être recontacté·e")
        if self.contact and "@" not in self.contact:
            raise ValueError("Le courriel de recontact n'a pas la forme attendue")
        if not self.contact:
            self.contact = None
        return self


class DemandeModif(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titre: str | None = None
    usage: str | None = None
    frequence: str | None = None
    service: str | None = None
    acces_actuel: str | None = None

    @field_validator("frequence")
    @classmethod
    def _frequence(cls, v):
        if v is not None and v not in FREQUENCES_DEMANDE:
            raise ValueError(f"La fréquence est l'une de : {', '.join(FREQUENCES_DEMANDE)}")
        return v


class SoutienEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = "soutien"
    temps_declare_min: int | None = None

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ROLES_SOUTIEN:
            raise ValueError(f"Le rôle est l'un de : {', '.join(ROLES_SOUTIEN)}")
        return v

    @field_validator("temps_declare_min")
    @classmethod
    def _temps(cls, v):
        if v is not None and not 0 <= v <= 100000:
            raise ValueError("Le temps déclaré est en minutes, entre 0 et 100 000")
        return v


class ClotureEntree(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doublon_de: str | None = None
    motif: str | None = None

    @model_validator(mode="after")
    def _motivee(self):
        if not self.doublon_de and not (self.motif or "").strip():
            raise ValueError("Une clôture est motivée : un doublon ou un motif")
        return self


def _404(e: store.Introuvable):
    return HTTPException(status_code=404, detail=f"Demande introuvable : {e}")


@router.get("")
async def lister(moi: Identite = Depends(identite), etat: str | None = Query(None), q: str | None = Query(None)):
    demandes = await store.lister_demandes(moi.hash, etat)
    if q and q.strip():
        demandes = doublons.candidats(q.strip(), [d for d in demandes if d["etat"] != "close"])
    return {"demandes": demandes, "seuil_chantier": (await capacites.lire_async())["seuil_chantier"]}


@router.post("", status_code=201)
async def deposer(entree: DemandeEntree, moi: Identite = Depends(identite)):
    seuil = int((await capacites.lire_async())["seuil_chantier"])
    demande = await store.creer_demande(entree.model_dump(), moi.hash, seuil)
    return {"demande": demande}


@router.get("/{ident}")
async def lire(ident: str, moi: Identite = Depends(identite)):
    try:
        return {"demande": await store.lire_demande(ident, moi.hash)}
    except store.Introuvable as e:
        raise _404(e)


@router.patch("/{ident}")
async def modifier(ident: str, entree: DemandeModif, moi: Identite = Depends(identite)):
    try:
        auteur = await store.auteur_de(ident)
    except store.Introuvable as e:
        raise _404(e)
    if auteur != moi.hash and not moi.superadmin:
        raise HTTPException(status_code=403, detail="Seule la personne qui a déposé la demande peut la modifier")
    champs = {k: v.strip() if isinstance(v, str) else v for k, v in entree.model_dump(exclude_none=True).items()}
    if not champs:
        raise HTTPException(status_code=422, detail="Rien à modifier")
    return {"demande": await store.modifier_demande(ident, champs, moi.hash)}


@router.post("/{ident}/soutenir")
async def soutenir(ident: str, entree: SoutienEntree, moi: Identite = Depends(identite)):
    try:
        demande = await store.soutenir(ident, moi.hash, entree.role, entree.temps_declare_min)
    except store.Introuvable as e:
        raise _404(e)
    except store.Conflit as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"demande": demande}


@router.delete("/{ident}/soutenir")
async def retirer_soutien(ident: str, moi: Identite = Depends(identite)):
    try:
        return {"demande": await store.retirer_soutien(ident, moi.hash)}
    except store.Introuvable as e:
        raise _404(e)


@router.delete("/{ident}/garant")
async def retirer_garant(ident: str, moi: Identite = Depends(identite)):
    if not moi.superadmin:
        raise HTTPException(status_code=403, detail="Retirer un garant est réservé à l'administration")
    try:
        return {"demande": await store.retirer_garant(ident, moi.hash)}
    except store.Introuvable as e:
        raise _404(e)


@router.post("/{ident}/abonner")
async def abonner(ident: str, moi: Identite = Depends(identite)):
    try:
        await store.auteur_de(ident)
    except store.Introuvable as e:
        raise _404(e)
    return {"abonne": await store.abonner("demande", ident, moi.hash, True)}


@router.delete("/{ident}/abonner")
async def desabonner(ident: str, moi: Identite = Depends(identite)):
    return {"abonne": await store.abonner("demande", ident, moi.hash, False)}


@router.get("/{ident}/journal")
async def journal(ident: str, moi: Identite = Depends(identite),
                  limite_: int = Depends(limite), avant: datetime | None = Depends(date_avant)):
    try:
        await store.auteur_de(ident)
    except store.Introuvable as e:
        raise _404(e)
    return await store.journal_de("demande", ident, limite_, avant)


@router.post("/{ident}/clore")
async def clore(ident: str, entree: ClotureEntree, moi: Identite = Depends(identite)):
    try:
        demande = await store.lire_demande(ident, moi.hash)
        auteur = await store.auteur_de(ident)
    except store.Introuvable as e:
        raise _404(e)
    if not (moi.superadmin or auteur == moi.hash or demande.get("mon_role") == "garant"):
        raise HTTPException(status_code=403, detail="Clore une demande revient à son auteur, à son garant ou à l'administration")
    try:
        return {"demande": await store.clore_demande(ident, moi.hash, entree.doublon_de, (entree.motif or "").strip() or None)}
    except store.Introuvable as e:
        raise _404(e)
