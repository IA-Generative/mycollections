"""Reposer les fiches de l'assistant après un changement de titre ou de catégorie."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers._collectif_commun import Identite, exiger_superadmin
from app.services import fiche_assistant
from app.services.owui_client import OwuiAdminUnavailable

router = APIRouter(prefix="/api/publications", tags=["Publication"])


@router.post("/resynchroniser")
async def resynchroniser(a_sec: bool = Query(False, description="Dire ce qui partirait, sans rien écrire"),
                         moi: Identite = Depends(exiger_superadmin)):
    """Toutes les collections publiées dans l'assistant : nom = titre, étiquette = catégorie.
    Ne touche ni au prompt ni aux outils des fiches (owui_client.fusionner_fiche)."""
    try:
        return await fiche_assistant.resynchroniser_toutes(a_sec=a_sec)
    except OwuiAdminUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
