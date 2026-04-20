"""QRCache HTTP surface — used by the playground to promote a question+answer
to the cache without going through a Feedback row first (e.g. the user voted
👍 on a response generated from an auto-seed question, not from an OWUI
complaint). Promotion from a Feedback still goes through
POST /api/feedback/{col}/{fbid}/promote.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.qr_cache import QRCache

router = APIRouter(prefix="/api/qr-cache", tags=["QRCache"])


class AddRequest(BaseModel):
    question: str
    answer: str
    tags: list[str] = []
    source: str = "manual"  # manual | feedback | import


@router.get("/{collection}")
async def list_entries(collection: str):
    cache = QRCache()
    return {"entries": [e.to_dict() for e in cache.list(collection)]}


@router.post("/{collection}")
async def add_entry(collection: str, req: AddRequest):
    cache = QRCache()
    entry = cache.add(collection, req.question, req.answer, req.tags, req.source)
    return {"status": "added", "entry": entry.to_dict()}


@router.delete("/{collection}/{entry_id}")
async def delete_entry(collection: str, entry_id: str):
    cache = QRCache()
    cache.delete(collection, entry_id)
    return {"status": "deleted"}
