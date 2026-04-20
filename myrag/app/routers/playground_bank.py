"""Playground bank — aggregated test-question bank for a collection.

Consolidates 4 sources into one flat list the frontend can render in the
playground's right column:

- 🤖 generated  : questions auto-produced by /generate-eval (stored as
                  EvalDataset rows with name ending in '-generated')
- 📄 imported   : EvalDataset rows created from the wizard step-4 JSON import
- 👎 fb_neg     : Feedback rows with rating < 0 (the real complaints)
- 👍 promoted   : QRCache entries with source == "feedback" (curated answers)

The bank is the READ surface. Writes go through existing endpoints:
- POST /api/feedback/ingest (👎)
- POST /api/feedback/{col}/{fbid}/promote (👍 from a feedback)
- POST /api/qr-cache/{col} (👍 manual — see qr_cache_router)
- POST /api/playground/{col}/generate-eval (auto-seed)
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from sqlalchemy import select

from app.database import async_session
from app.models.db import EvalDataset, Feedback
from app.services.qr_cache import QRCache

router = APIRouter(prefix="/api/playground", tags=["Playground"])


@router.get("/{collection}/bank")
async def get_bank(collection: str):
    """Return the aggregated question bank for a collection.

    Empty bank is a valid answer — the caller decides whether to auto-seed.
    """
    items: list[dict] = []
    stats = {"total": 0, "generated": 0, "imported": 0, "fb_neg": 0, "promoted": 0}

    async with async_session() as session:
        # EvalDatasets — each stored dataset can contain N questions. We flatten.
        ds_result = await session.execute(
            select(EvalDataset).where(EvalDataset.collection_name == collection)
        )
        for ds in ds_result.scalars().all():
            questions = json.loads(ds.questions_json or "[]")
            # Convention: if the dataset name ends with "-generated" (or the
            # description mentions "automatique") we tag it as generated,
            # otherwise imported. The wizard step-4 import path uses custom
            # names; auto-generate uses "<collection>-evaluation" +
            # description "Jeu de test genere automatiquement".
            is_generated = (
                "genere" in (ds.description or "").lower()
                or "auto" in (ds.name or "").lower()
                or ds.name.endswith("-evaluation")
            )
            source = "generated" if is_generated else "imported"
            for q in questions:
                items.append({
                    "id": f"eval_{ds.id}_{q.get('id', '')}",
                    "question": q.get("question", ""),
                    "expected_answer": q.get("expected_answer", ""),
                    "source": source,
                    "metadata": {
                        "dataset_id": ds.id,
                        "dataset_name": ds.name,
                        "must_cite": q.get("must_cite", []),
                        "tags": q.get("tags", []),
                        "out_of_scope": q.get("out_of_scope", False),
                        "created_at": ds.created_at.isoformat() if ds.created_at else "",
                    },
                })
                stats[source] += 1

        # Feedback with negative rating — the real complaints to surface.
        fb_result = await session.execute(
            select(Feedback)
            .where(Feedback.collection_name == collection)
            .where(Feedback.rating < 0)
            .order_by(Feedback.created_at.desc())
        )
        for fb in fb_result.scalars().all():
            items.append({
                "id": f"fb_{fb.id}",
                "question": fb.question,
                "expected_answer": "",
                "source": "fb_neg",
                "metadata": {
                    "feedback_id": fb.id,
                    "rating": fb.rating,
                    "reason": fb.reason,
                    "response": fb.response,
                    "status": fb.status,
                    "owui_chat_id": fb.owui_chat_id,
                    "created_at": fb.created_at.isoformat() if fb.created_at else "",
                },
            })
            stats["fb_neg"] += 1

    # Promoted Q&R from QRCache (file-backed, not DB).
    try:
        cache = QRCache()
        for entry in cache.list(collection):
            if entry.source == "feedback":
                items.append({
                    "id": f"qr_{entry.id}",
                    "question": entry.question,
                    "expected_answer": entry.answer,
                    "source": "promoted",
                    "metadata": {
                        "qr_id": entry.id,
                        "tags": entry.tags,
                        "created_at": entry.created_at,
                    },
                })
                stats["promoted"] += 1
    except Exception:
        # QRCache is best-effort; missing data_dir shouldn't break the bank.
        pass

    stats["total"] = len(items)
    return {"items": items, "stats": stats}
