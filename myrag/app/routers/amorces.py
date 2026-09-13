"""Les amorces : le catalogue, et l'import idempotent qui crée la collection en
état « amorcée », garant pressenti et grille pré-remplie. Les connecteurs arrivent
aux lots 0 et 5 ; tant qu'un connecteur manque, l'import le NOMME (501)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.amorces import charger_catalogue, entree
from app.routers._collectif_commun import Identite, identite
from app.services import collectif_store as store
from app.services.collection_store import create_collection as db_create_collection
from app.services.collection_store import get_collection as db_get_collection

router = APIRouter(prefix="/api/amorces", tags=["Amorces"])

#: Les connecteurs d'import, par nom du catalogue. Vide au lot 1 — exprès.
CONNECTEURS: dict[str, object] = {}


def _fusion(e: dict, etat: dict | None) -> dict:
    return {**e, "etat_import": "jamais", "collection_name": None, "dernier_import_le": None, "erreur": None,
            **{k: v for k, v in (etat or {}).items() if k != "id"}}


@router.get("")
async def lister(moi: Identite = Depends(identite)):
    etats_ = await store.etats_des_amorces()
    return {"amorces": [_fusion(e, etats_.get(e["id"])) for e in charger_catalogue()]}


@router.post("/{ident}/import")
async def importer(ident: str, moi: Identite = Depends(identite)):
    if not moi.superadmin:
        raise HTTPException(status_code=403, detail="L'import d'une amorce est réservé à l'administration")
    e = entree(ident)
    if not e:
        raise HTTPException(status_code=404, detail=f"Amorce inconnue : {ident}")
    name = e["collection"]
    if not await db_get_collection(name):
        await db_create_collection({
            "name": name, "description": e.get("description", ""), "scope": "group",
            "scope_groups_json": "[]", "created_by": "", "source_type": e.get("connecteur", ""),
            "source_url": e.get("source_url", ""),
        })
        await store.initialiser_collection(name, None, garant_pressenti=e.get("garant_pressenti", ""),
                                           grille=e.get("grille"), robot="amorce")
    connecteur = CONNECTEURS.get(e.get("connecteur", ""))
    if connecteur is None:
        erreur = f"connecteur « {e.get('connecteur')} » non implémenté pour l'amorce {ident} (lot 0 / lot 5)"
        await store.marquer_amorce(ident, "echec", collection_name=name, erreur=erreur)
        raise HTTPException(status_code=501, detail=erreur)
    await store.marquer_amorce(ident, "en_cours", collection_name=name)
    try:
        resultat = await connecteur(name, e)  # type: ignore[operator]
    except Exception as ex:  # noqa: BLE001 — l'échec se consigne, il ne se perd pas
        await store.marquer_amorce(ident, "echec", collection_name=name, erreur=str(ex))
        raise HTTPException(status_code=502, detail=f"Import de {ident} échoué : {ex}")
    await store.marquer_amorce(ident, "termine", collection_name=name, detail=resultat)
    await store.consigner("collection", name, "import.termine", robot=f"amorce:{ident}", collection_name=name, detail=resultat)
    return {"amorce": ident, "collection": name, "resultat": resultat}
