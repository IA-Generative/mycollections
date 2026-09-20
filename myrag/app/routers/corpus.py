"""Consulter le corpus d'une collection : ses documents, puis le texte de l'un d'eux.

Deux routes en lecture, toutes deux derrière `collection_lisible` : qui ne peut pas lire
la collection reçoit 404, comme si elle n'existait pas. Le jeton d'administration
d'OpenRAG reste côté serveur — c'est cette garde, et elle seule, qui décide de ce qu'un
appelant peut lire.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers._collectif_commun import collection_lisible
from app.security_utils import reject_path_traversal
from app.services import corpus
from app.services.morceau import decouper_morceau
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/collections", tags=["Corpus"])

_LECTURES_PARALLELES = 8


@router.get("/{name}/documents")
async def lister_documents(
    name: str,
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    par_page: int = Query(corpus.PAR_PAGE_DEFAUT, ge=1, le=corpus.PAR_PAGE_MAX),
    fiche: dict = Depends(collection_lisible),
):
    """Une page des documents du corpus, cherchés par titre, nom de fichier ou identifiant."""
    try:
        fichiers = await corpus.fichiers_de(OpenRAGClient(), name)
    except Exception:
        raise HTTPException(status_code=502, detail="Le corpus n'a pas pu être lu : OpenRAG ne répond pas.")
    return corpus.chercher_et_paginer(fichiers, q=q, page=page, par_page=par_page)


@router.get("/{name}/documents/{file_id:path}")
async def lire_document(name: str, file_id: str, fiche: dict = Depends(collection_lisible)):
    """Le texte d'un document : ses morceaux, dans l'ordre, sans leurs balises techniques."""
    reject_path_traversal(file_id, field="file_id")
    client = OpenRAGClient()
    try:
        detail = await client.file_detail(name, file_id)
    except Exception:
        raise HTTPException(status_code=502, detail="Le document n'a pas pu être lu : OpenRAG ne répond pas.")
    if detail is None:
        raise HTTPException(status_code=404, detail="Document introuvable dans cette collection")

    meta = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
    # La partition lue doit être celle de la collection autorisée — jamais celle d'à côté.
    if meta.get("partition") not in (None, name):
        raise HTTPException(status_code=404, detail="Document introuvable dans cette collection")

    ids = corpus.identifiants_des_morceaux(detail)
    a_lire = ids[:corpus.MORCEAUX_MAX]
    verrou = asyncio.Semaphore(_LECTURES_PARALLELES)

    async def lire(cid: str) -> dict | None:
        async with verrou:
            try:
                return await client.extract(cid)
            except Exception:
                return None

    lus = await asyncio.gather(*(lire(cid) for cid in a_lire))
    morceaux, contexte = [], ""
    for cid, brut in zip(a_lire, lus):
        if not brut:
            continue
        ctx, _fichier, corps = decouper_morceau(str(brut.get("page_content") or brut.get("content") or brut.get("text") or ""))
        contexte = contexte or ctx
        source = brut.get("metadata") if isinstance(brut.get("metadata"), dict) else {}
        page = brut.get("page", source.get("page"))
        if corps:
            morceaux.append({"id": cid, "texte": corps, "page": page if page not in ("", None) else None})

    resume = corpus.resumer_fichier({**meta, "file_id": file_id})
    return {
        **resume,
        "contexte": contexte,
        "morceaux": morceaux,
        "total_morceaux": len(ids),
        "illisibles": len(a_lire) - len(morceaux),
        "tronque": len(ids) > len(a_lire),
    }
