"""Feedback router — ingest, review, promote user feedback (DB-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import CurrentUser, current_user
from app.routers.publication import _fiche_pour
from app.services.feedback_store import (
    feedback_stats as db_stats,
)
from app.services.feedback_store import (
    get_feedback as db_get,
)
from app.services.feedback_store import (
    ingest_feedback as db_ingest,
)
from app.services.feedback_store import (
    list_feedback as db_list,
)
from app.services.feedback_store import (
    promote_feedback as db_promote,
)
from app.services.feedback_store import (
    review_feedback as db_review,
)

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


class IngestRequest(BaseModel):
    collection: str
    question: str
    response: str
    rating: int
    reason: str = ""
    owui_chat_id: str = ""
    owui_message_id: str = ""


class ReviewRequest(BaseModel):
    status: str = "reviewed"
    reviewed_by: str = ""


class PromoteRequest(BaseModel):
    promote_to: str  # qr | eval
    corrected_answer: str = ""


@router.post("/ingest")
async def ingest_feedback_endpoint(req: IngestRequest, user: CurrentUser = Depends(current_user)):
    # Donner un avis sur une collection demande de pouvoir la lire.
    await _fiche_pour(req.collection, user, ecrire=False)
    fb = await db_ingest(
        collection=req.collection,
        question=req.question,
        response=req.response,
        rating=req.rating,
        reason=req.reason,
        owui_chat_id=req.owui_chat_id,
        owui_message_id=req.owui_message_id,
    )
    return {"status": "ingested", "id": fb["id"]}


@router.get("/{collection}")
async def list_feedback_endpoint(
    collection: str,
    status: str | None = Query(None),
    rating: int | None = Query(None),
    user: CurrentUser = Depends(current_user),
):
    # Les questions et réponses des utilisateurs : réservées à qui GÈRE la collection.
    await _fiche_pour(collection, user, ecrire=True)
    items = await db_list(collection, status=status, rating=rating)
    return {"feedback": items}


@router.get("/{collection}/stats")
async def feedback_stats_endpoint(collection: str, user: CurrentUser = Depends(current_user)):
    await _fiche_pour(collection, user, ecrire=False)
    return await db_stats(collection)


@router.patch("/{collection}/{feedback_id}/review")
async def review_feedback_endpoint(collection: str, feedback_id: int, req: ReviewRequest, user: CurrentUser = Depends(current_user)):
    await _fiche_pour(collection, user, ecrire=True)
    fb = await db_get(feedback_id)
    if not fb or fb.get("collection") != collection:
        raise HTTPException(status_code=404, detail="Feedback not found")
    result = await db_review(feedback_id, status=req.status, reviewed_by=req.reviewed_by or user.username)
    if not result:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "updated"}


@router.post("/{collection}/{feedback_id}/promote")
async def promote_feedback_endpoint(collection: str, feedback_id: int, req: PromoteRequest, user: CurrentUser = Depends(current_user)):
    await _fiche_pour(collection, user, ecrire=True)
    fb = await db_get(feedback_id)
    if not fb or fb.get("collection") != collection:
        raise HTTPException(status_code=404, detail="Feedback not found")

    await db_promote(feedback_id, promote_to=req.promote_to)

    # L'avis devient une question du jeu de questions (docs/qualite.md). Avec une réponse corrigée
    # (« réponse validée » de l'écran), elle est validée et sa réponse est fiable.
    from app.services import questions_store
    from app.services.collectif_store import Conflit

    reponse = (req.corrected_answer or "").strip()
    try:
        q = await questions_store.creer_question(
            collection,
            {"question": fb["question"], "reponse": reponse, "relecture": "valide" if reponse else "brut"},
            user.sub,
            origine="avis",
            source_ref=f"feedback:{feedback_id}",
            feedback_id=feedback_id,
        )
        if reponse and req.promote_to == "qr":
            await questions_store.modifier_question(collection, q.id, questions_store.QuestionModification(fiable=True), user.sub)
    except Conflit:
        pass  # déjà dans le jeu : la promotion ne crée pas de doublon

    return {"status": "promoted", "promote_to": req.promote_to}
