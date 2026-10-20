"""Les assistants de recherche (ADR-0003) : la fiche, son brouillon et ses versions.

Le harnais (lot A) ajoute ici, et sous /api/v1/assistants, le plan, l'exécution, les réponses
fiables et la qualité ; ce routeur ne fait que lire et écrire la fiche.

Droits, calculés ici à partir du jeton — jamais d'un paramètre du client :
- VOIR un assistant : au moins une de ses sources `collection` est lisible, ou l'on en est le
  créateur, ou l'on administre ; une source illisible n'est pas montrée (un compte, pas un nom) ;
- MODIFIER ou PUBLIER : pouvoir gérer TOUTES ses sources `collection` (et, pour un assistant
  sans collection, en être le créateur), avant comme après la modification ;
- une source `connecteur` n'ouvre aucun droit : le catalogue des connecteurs arrive au lot A.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.harnais.contrat import FicheAssistant
from app.routers._commun import Identite, capacite, identite
from app.services import assistant_droits as droits_service
from app.services import assistant_store as store

router = APIRouter(prefix="/api/assistants", tags=["assistants"], dependencies=[Depends(capacite("assistants"))])


async def _collections(fiche: FicheAssistant) -> dict[str, dict | None]:
    return await droits_service.collections_de(fiche)


def _lisible(col: dict | None, moi: Identite) -> bool:
    return droits_service.lisible(col, moi.user)


async def _droits(fiche: FicheAssistant, createur_hash: str | None, moi: Identite) -> tuple[bool, bool, dict[str, dict | None]]:
    """(voir, modifier, collections) pour cette fiche et cette personne."""
    return await droits_service.droits(fiche, createur_hash, user=moi.user, hash_=moi.hash, superadmin=moi.superadmin)


def _vue(fiche: FicheAssistant, cols: dict[str, dict | None], moi: Identite, modifier: bool) -> tuple[dict, int]:
    """La fiche telle que la personne peut la lire : sans les collections qu'elle ne lit pas."""
    d = fiche.model_dump(mode="json")
    if modifier:
        return d, 0
    gardees = [s for s in d["sources"] if s["type"] != "collection" or _lisible(cols.get(s["id"]), moi)]
    masquees = len(d["sources"]) - len(gardees)
    ids = {s["id"] for s in gardees}
    d["sources"] = gardees
    for c in d["consignes"]:
        c["chercher"] = [e for e in c["chercher"] if e["source"] in ids]
    return d, masquees


async def _charger(ident: str, moi: Identite) -> tuple[dict, FicheAssistant, bool, dict]:
    """L'assistant si la personne peut le voir ; 404 sinon (ne pas divulguer son existence)."""
    ligne = await store.lire(ident)
    if ligne is None:
        raise HTTPException(status_code=404, detail=f"Assistant « {ident} » introuvable")
    fiche = FicheAssistant.model_validate(ligne["fiche"])
    voir, modifier, cols = await _droits(fiche, ligne.get("cree_par_hash"), moi)
    if not voir:
        raise HTTPException(status_code=404, detail=f"Assistant « {ident} » introuvable")
    return ligne, fiche, modifier, cols


def _reponse(ligne: dict, fiche: FicheAssistant, cols: dict, moi: Identite, modifier: bool) -> dict:
    vue, masquees = _vue(fiche, cols, moi, modifier)
    assistant = {k: v for k, v in ligne.items() if k not in ("fiche", "sources", "cree_par_hash")}
    return {"assistant": assistant, "fiche": vue, "version": ligne["version_publiee"], "sources_masquees": masquees, "mes_droits": {"ecrire": modifier}}


@router.get("")
async def lister(moi: Identite = Depends(identite)):
    """Les assistants que la personne peut voir (hors ceux en sommeil)."""
    sortie = []
    for a in await store.lister():
        ligne = await store.lire(a["id"])
        fiche = FicheAssistant.model_validate(ligne["fiche"])
        voir, modifier, cols = await _droits(fiche, ligne.get("cree_par_hash"), moi)
        if not voir:
            continue
        vue, masquees = _vue(fiche, cols, moi, modifier)
        sortie.append(
            {
                "id": a["id"],
                "titre": a["titre"],
                "rubrique": a["rubrique"],
                "description": a["description"],
                "version": a["version_publiee"],
                "collection_name": a["collection_name"],
                "sources": vue["sources"],
                "sources_masquees": masquees,
                "publication": a["publication"],
                "mes_droits": {"ecrire": modifier},
            }
        )
    return {"assistants": sortie}


@router.get("/{ident}")
async def lire(ident: str, moi: Identite = Depends(identite)):
    ligne, fiche, modifier, cols = await _charger(ident, moi)
    return _reponse(ligne, fiche, cols, moi, modifier)


@router.put("/{ident}")
async def enregistrer(ident: str, fiche: FicheAssistant, moi: Identite = Depends(identite)):
    """Crée l'assistant ou remplace son brouillon. Publier en fait une version (POST …/publier)."""
    if fiche.assistant != ident:
        raise HTTPException(status_code=422, detail="L'identifiant de la fiche diffère de celui de l'adresse")
    existante = await store.lire(ident)
    if existante is not None:
        _, _, modifier_avant, _ = await _charger(ident, moi)
        if not modifier_avant:
            raise HTTPException(status_code=403, detail="Modifier cet assistant demande de gérer toutes ses collections")
    cols = await _collections(fiche)
    inconnues = sorted(n for n, c in cols.items() if c is None)
    if inconnues:
        raise HTTPException(status_code=422, detail=f"Source inconnue : {', '.join(inconnues)}")
    createur = existante.get("cree_par_hash") if existante else moi.hash
    _, modifier, cols = await _droits(fiche, createur, moi)
    if not modifier:
        raise HTTPException(status_code=403, detail="Assembler un assistant demande de gérer chacune de ses collections")
    await store.enregistrer_brouillon(fiche, auteur_hash=moi.hash)
    ligne, fiche_lue, modifier, cols = await _charger(ident, moi)
    return _reponse(ligne, fiche_lue, cols, moi, modifier)


@router.post("/{ident}/publier")
async def publier(ident: str, moi: Identite = Depends(identite)):
    """Fige le brouillon en version (une version de plus seulement si son contenu a changé)."""
    _, _, modifier, _ = await _charger(ident, moi)
    if not modifier:
        raise HTTPException(status_code=403, detail="Publier cet assistant demande de gérer toutes ses collections")
    return await store.publier(ident, auteur_hash=moi.hash)


@router.get("/{ident}/versions")
async def versions(ident: str, moi: Identite = Depends(identite)):
    await _charger(ident, moi)
    return {"versions": await store.versions(ident)}
