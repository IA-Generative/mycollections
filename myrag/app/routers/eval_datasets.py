"""EvalDataset persistence — lets the playground bank store auto-generated
and imported question sets. The wizard step-4 historically kept its JSON
in-memory / localStorage; this router exposes the DB-backed CRUD so the
playground can READ what the wizard (eventually) writes and WRITE the result
of /generate-eval so it survives reloads.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import async_session
from app.models.db import EvalDataset

router = APIRouter(prefix="/api/eval", tags=["Eval"])


class DatasetRequest(BaseModel):
    name: str
    description: str = ""
    questions: list[dict]


@router.get("/{collection}/datasets")
async def list_datasets(collection: str):
    async with async_session() as session:
        result = await session.execute(
            select(EvalDataset)
            .where(EvalDataset.collection_name == collection)
            .order_by(EvalDataset.created_at.desc())
        )
        return {"datasets": [d.to_dict() for d in result.scalars().all()]}


@router.post("/{collection}/datasets")
async def create_dataset(collection: str, req: DatasetRequest):
    async with async_session() as session:
        ds = EvalDataset(
            collection_name=collection,
            name=req.name,
            description=req.description,
            questions_json=json.dumps(req.questions, ensure_ascii=False),
        )
        session.add(ds)
        await session.commit()
        await session.refresh(ds)
        return ds.to_dict()


@router.delete("/{collection}/datasets/{dataset_id}")
async def delete_dataset(collection: str, dataset_id: int):
    async with async_session() as session:
        ds = await session.get(EvalDataset, dataset_id)
        if not ds or ds.collection_name != collection:
            raise HTTPException(status_code=404, detail="Dataset not found")
        await session.delete(ds)
        await session.commit()
        return {"status": "deleted"}
