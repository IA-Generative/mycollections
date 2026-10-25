"""Ce que Mes collections offre aux pages des autres : les sites déclarés, lus par l'extension
du navigateur (la bulle « + IA »), et à terme la fenêtre de recherche à insérer dans une
application (lot C). Routeur monté SANS la garde commune : chaque route déclare la sienne.

- `GET /api/v1/sites` : les motifs d'adresse des collections et assistants que la personne lit.
  Route du contrat externe : elle vérifie l'audience du jeton, comme la recherche v1. Sans jeton :
  401, ou, si `MYCOLLECTIONS_SITES_ANONYMES` est vrai (débogage), les sites des seules collections
  ouvertes à tous, marqués `"anonyme": true`.
- `GET|PUT /api/collections/{name}/sites` et `GET|PUT /api/assistants/{ident}/sites` : les motifs
  d'une fiche, lus par qui la lit, remplacés par qui la gère.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.auth import CurrentUser, _bearer_scheme, audience_acceptee, current_user, verify_jwt
from app.config import settings
from app.routers._commun import Identite, capacite, identite
from app.services import access, assistant_droits, assistant_recherche, assistant_store, sites
from app.services.collection_store import get_collection
from app.services.nommage import titre_de

logger = logging.getLogger("myrag.sites")


class _ReponseAnonyme(Exception):
    """Levée par `_anonyme` avant toute autre dépendance : la réponse sans jeton est déjà prête."""

    def __init__(self, corps: dict):
        self.corps = corps


class _RouteFenetre(APIRoute):
    """Rend la réponse anonyme préparée par `_anonyme` (les autres dépendances, qui exigent un
    jeton, ne sont alors pas jouées)."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def gestionnaire(request: Request) -> Response:
            try:
                return await original(request)
            except _ReponseAnonyme as e:
                return JSONResponse(e.corps, headers={"Cache-Control": "no-store"})

        return gestionnaire


router = APIRouter(tags=["fenetre"], route_class=_RouteFenetre)


async def _anonyme(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> None:
    """Sans jeton : 401, ou la liste anonyme si elle est permise. Jouée avant les dépendances
    d'identité (FastAPI résout les dépendances de la route en premier)."""
    if not settings.auth_enabled or (credentials is not None and credentials.credentials):
        return
    if not settings.sites_anonymes:
        raise HTTPException(status_code=401, detail="Authentification requise")
    raise _ReponseAnonyme(await _liste_anonyme())


async def _liste_anonyme() -> dict:
    """Les sites des collections ouvertes à tous (`scope` public, non archivées). Aucun assistant :
    ses droits dépendent de la personne."""
    regroupes: dict[str, list[dict]] = {}
    fiches: dict[str, dict | None] = {}
    for type_, ident, motif in await sites.tous():
        if type_ != "collection":
            continue
        if ident not in fiches:
            fiches[ident] = await get_collection(ident)
        col = fiches[ident]
        if not col or col.get("archived_at") or col.get("scope") != "public":
            continue
        regroupes.setdefault(motif, []).append({"type": "collection", "id": ident, "titre": titre_de(col)})
    return {"ttl_s": sites.TTL_S, "anonyme": True, "sites": [{"motif": m, "cibles": c} for m, c in sorted(regroupes.items())]}


def _audience(claims: dict = Depends(verify_jwt)) -> None:
    """Un jeton émis pour un autre service n'ouvre pas la liste des sites."""
    if settings.auth_enabled and not audience_acceptee(claims):
        logger.warning("Sites refusés : audience non acceptée (azp=%s)", str(claims.get("azp", ""))[:64])
        raise HTTPException(status_code=403, detail={"code": "audience_mismatch", "message": "Ce jeton n'est pas destiné à Mes collections"})


class Motifs(BaseModel):
    motifs: list[str] = Field(default_factory=list, max_length=100)


def _valider(corps: Motifs) -> list[str]:
    try:
        return sites.valider_motifs(corps.motifs)
    except sites.MotifInvalide as e:
        raise HTTPException(status_code=422, detail={"reason": "motif", "message": str(e)})


# ─── La liste lue par l'extension ────────────────────────────────────────────────────────────


@router.get("/api/v1/sites", dependencies=[Depends(_anonyme), Depends(_audience)])
async def sites_declares(moi: Identite = Depends(identite)) -> dict:
    """Les motifs, regroupés, avec les cibles que la personne LIT. Une cible illisible, archivée,
    ou un assistant jamais publié qu'elle ne gère pas : absente, sans le dire."""
    titres: dict[tuple[str, str], str | None] = {}
    regroupes: dict[str, list[dict]] = {}
    assistants_allumes = None
    for type_, ident, motif in await sites.tous():
        cle = (type_, ident)
        if cle not in titres:
            if type_ == "assistant" and assistants_allumes is None:
                try:
                    await capacite("assistants")()
                    assistants_allumes = True
                except HTTPException:
                    assistants_allumes = False
            titres[cle] = await _titre_lisible(type_, ident, moi, assistants_allumes)
        if titres[cle] is None:
            continue
        regroupes.setdefault(motif, []).append({"type": type_, "id": ident, "titre": titres[cle]})
    return {"ttl_s": sites.TTL_S, "anonyme": False, "sites": [{"motif": m, "cibles": c} for m, c in sorted(regroupes.items())]}


async def _titre_lisible(type_: str, ident: str, moi: Identite, assistants_allumes: bool | None) -> str | None:
    if type_ == "collection":
        from app.services import sensibilite

        col = await get_collection(ident)
        # Le plafond de sensibilité de l'extension (MYCOLLECTIONS_DESTINATIONS_SENSIBILITE_MAX).
        if col and not sensibilite.admise(col.get("sensitivity"), "navigateur"):
            return None
        return titre_de(col) if assistant_droits.lisible(col, moi.user) else None
    if not assistants_allumes:
        return None
    try:
        charge = await assistant_recherche.charger(ident, moi.user, moi.hash, moi.superadmin, brouillon=True)
    except assistant_recherche.AssistantIntrouvable:
        return None
    return charge.fiche.titre


# ─── Les motifs d'une collection ─────────────────────────────────────────────────────────────


async def _collection(name: str, user: CurrentUser, *, ecrire: bool) -> dict:
    col = await get_collection(name)
    if not col or not assistant_droits.lisible(col, user):
        raise HTTPException(status_code=404, detail=f"Collection « {name} » introuvable")
    if ecrire and not access.can_write(name=col["name"], created_by=col["created_by"], user_groups=user.groups, user_sub=user.sub):
        raise HTTPException(status_code=403, detail="Seules les personnes qui gèrent la collection déclarent ses sites")
    return col


@router.get("/api/collections/{name}/sites")
async def sites_collection(name: str, user: CurrentUser = Depends(current_user)) -> dict:
    await _collection(name, user, ecrire=False)
    return {"motifs": await sites.lire("collection", name), "max": sites.MOTIFS_MAX}


@router.put("/api/collections/{name}/sites")
async def declarer_sites_collection(name: str, corps: Motifs, user: CurrentUser = Depends(current_user)) -> dict:
    await _collection(name, user, ecrire=True)
    return {"motifs": await sites.remplacer("collection", name, _valider(corps)), "max": sites.MOTIFS_MAX}


# ─── Les motifs d'un assistant ───────────────────────────────────────────────────────────────


async def _assistant(ident: str, moi: Identite, *, ecrire: bool) -> None:
    ligne = await assistant_store.lire(ident)
    if ligne is None:
        raise HTTPException(status_code=404, detail=f"Assistant « {ident} » introuvable")
    from app.harnais.contrat import FicheAssistant

    fiche = FicheAssistant.model_validate(ligne["fiche"])
    voir, modifier, _ = await assistant_droits.droits(fiche, ligne.get("cree_par_hash"), user=moi.user, hash_=moi.hash, superadmin=moi.superadmin)
    if not voir:
        raise HTTPException(status_code=404, detail=f"Assistant « {ident} » introuvable")
    if ecrire and not modifier:
        raise HTTPException(status_code=403, detail="Seules les personnes qui gèrent l'assistant déclarent ses sites")


@router.get("/api/assistants/{ident}/sites", dependencies=[Depends(capacite("assistants"))])
async def sites_assistant(ident: str, moi: Identite = Depends(identite)) -> dict:
    await _assistant(ident, moi, ecrire=False)
    return {"motifs": await sites.lire("assistant", ident), "max": sites.MOTIFS_MAX}


@router.put("/api/assistants/{ident}/sites", dependencies=[Depends(capacite("assistants"))])
async def declarer_sites_assistant(ident: str, corps: Motifs, moi: Identite = Depends(identite)) -> dict:
    await _assistant(ident, moi, ecrire=True)
    return {"motifs": await sites.remplacer("assistant", ident, _valider(corps)), "max": sites.MOTIFS_MAX}
