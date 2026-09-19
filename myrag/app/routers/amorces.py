"""Les amorces : le catalogue, et l'import idempotent qui crée la collection en
état « amorcée », garant pressenti, grille pré-remplie, vingt questions en banque,
puis fait tourner le connecteur. Un import long tourne en tâche de fond (202) ;
`?synchrone=true` l'attend (exploitation, tests). Tant qu'un connecteur manque,
l'import le NOMME (501)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.amorces import charger_catalogue, entree
from app.routers._collectif_commun import Identite, exiger_superadmin, identite
from app.services import collectif_store as store
from app.services.amorces import CONNECTEURS, ingestion
from app.services.amorces.banque import poser_questions
from app.services.collection_store import create_collection as db_create_collection
from app.services.collection_store import get_collection as db_get_collection
from app.services.collection_store import list_collections as db_list_collections

router = APIRouter(prefix="/api/amorces", tags=["Amorces"])
logger = logging.getLogger("myrag.amorces")

#: Critère d'ouverture de la section collaborative : N des amorces en contrôle (ou au-delà).
OUVERTURE_REQUIS = 3
_AVANCEES = ("en_controle", "publiee_groupe", "publiee_tous")
_taches: list[asyncio.Task] = []


def _fusion(e: dict, etat: dict | None, collection: dict | None) -> dict:
    return {**{k: v for k, v in e.items() if k != "questions"}, "nb_questions": len(e.get("questions", [])),
            "etat_import": "jamais", "collection_name": None, "dernier_import_le": None, "erreur": None, "detail": {},
            **{k: v for k, v in (etat or {}).items() if k != "id"},
            "etat_collab": (collection or {}).get("etat_collab")}


async def _ouverture(catalogue: list[dict], collections: dict[str, dict]) -> dict:
    avancees = [e["id"] for e in catalogue if (collections.get(e["collection"]) or {}).get("etat_collab") in _AVANCEES]
    return {"requis": OUVERTURE_REQUIS, "en_controle": len(avancees), "amorces": avancees,
            "ouverte": len(avancees) >= OUVERTURE_REQUIS}


@router.get("")
async def lister(moi: Identite = Depends(identite)):
    catalogue = charger_catalogue()
    etats_ = await store.etats_des_amorces()
    noms = {e["collection"] for e in catalogue}
    collections = {c["name"]: c for c in await db_list_collections(include_archived=True) if c["name"] in noms}
    return {"amorces": [_fusion(e, etats_.get(e["id"]), collections.get(e["collection"])) for e in catalogue],
            "ouverture": await _ouverture(catalogue, collections)}


async def _categorie_connue(cle: str | None) -> str | None:
    """La rubrique que propose le catalogue, si l'administration ne l'a pas retirée."""
    from app.services import categorie_store
    return cle if cle and any(c["cle"] == cle for c in await categorie_store.lister()) else None


async def _preparer(e: dict) -> str:
    """Crée la collection amorcée, sa grille pré-remplie et sa banque de questions — idempotent."""
    name = e["collection"]
    if not await db_get_collection(name):
        await db_create_collection({
            "name": name, "titre": e.get("titre", ""), "categorie": await _categorie_connue(e.get("categorie")),
            "description": e.get("description", ""), "scope": "group",
            "scope_groups_json": "[]", "created_by": "", "source_type": e.get("connecteur", ""),
            "source_url": e.get("source_url", ""),
        })
        await store.initialiser_collection(name, None, garant_pressenti=e.get("garant_pressenti", ""),
                                           grille=e.get("grille"), robot="amorce")
    await poser_questions(name, e.get("questions", []))
    return name


async def _executer(ident: str, e: dict, name: str, *, depuis_zero: bool = False) -> dict:
    """`depuis_zero` : après une purge, ce que l'import précédent disait avoir fait
    (les mois déjà importés de la justice administrative) ne compte plus."""
    connecteur = CONNECTEURS[e["connecteur"]]
    precedent = {} if depuis_zero else ((await store.etats_des_amorces()).get(ident) or {})
    contexte = {}
    if e["connecteur"] == "justice-administrative":
        contexte["deja_importes"] = (precedent.get("detail") or {}).get("couverture", {}).get("mois_importes", [])
    try:
        resultat = await connecteur(name, e, **contexte)
    except Exception as ex:  # noqa: BLE001 — l'échec se consigne, il ne se perd pas
        logger.warning("import de l'amorce %s échoué : %s", ident, ex)
        await store.marquer_amorce(ident, "echec", collection_name=name, erreur=str(ex))
        await store.consigner("collection", name, "import.echoue", robot=f"amorce:{ident}", collection_name=name,
                              detail={"erreur": str(ex)[:500]})
        raise
    if resultat.get("couverture"):
        await store.poser_couverture(name, resultat["couverture"], f"amorce:{ident}")
    await store.marquer_amorce(ident, "termine", collection_name=name, detail=resultat)
    await store.consigner("collection", name, "import.termine", robot=f"amorce:{ident}", collection_name=name,
                          detail={k: v for k, v in resultat.items() if k != "couverture"})
    return resultat


@router.post("/{ident}/import")
async def importer(ident: str, moi: Identite = Depends(exiger_superadmin), synchrone: bool = Query(False),
                   purger: bool = Query(False, description="Vider la partition et réindexer tout")):
    e = entree(ident)
    if not e:
        raise HTTPException(status_code=404, detail=f"Amorce inconnue : {ident}")
    name = await _preparer(e)
    if e.get("connecteur") not in CONNECTEURS:
        erreur = f"connecteur « {e.get('connecteur')} » non implémenté pour l'amorce {ident}"
        await store.marquer_amorce(ident, "echec", collection_name=name, erreur=erreur)
        raise HTTPException(status_code=501, detail=erreur)
    etat = (await store.etats_des_amorces()).get(ident) or {}
    if etat.get("etat_import") == "en_cours":
        raise HTTPException(status_code=409, detail=f"L'import de {ident} est déjà en cours")
    await store.marquer_amorce(ident, "en_cours", collection_name=name)
    if purger:
        # OpenRAG n'efface pas les morceaux d'un document : sans purge, un nouveau
        # découpage s'ajouterait aux anciens morceaux au lieu de les remplacer.
        await ingestion.purger(name)
        await store.consigner("collection", name, "import.purge", robot=f"amorce:{ident}", collection_name=name)
    if synchrone:
        try:
            resultat = await _executer(ident, e, name, depuis_zero=purger)
        except Exception as ex:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Import de {ident} échoué : {ex}")
        return {"amorce": ident, "collection": name, "etat_import": "termine", "resultat": resultat}
    tache = asyncio.create_task(_executer(ident, e, name, depuis_zero=purger))
    _taches.append(tache)
    tache.add_done_callback(lambda t: _taches.remove(t) if t in _taches else None)
    return {"amorce": ident, "collection": name, "etat_import": "en_cours"}
