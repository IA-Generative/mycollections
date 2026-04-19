"""Collection CRUD service backed by SQLAlchemy database."""

import logging
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.db import (
    Collection,
    utcnow,
    EvalDataset,
    EvalRun,
    Feedback,
    IngestJob,
    Publication,
    PublicationHistory,
    SourceFile,
)

logger = logging.getLogger("myrag.collection_store")


async def list_collections(include_archived: bool = False) -> list[dict]:
    async with async_session() as session:
        stmt = select(Collection).order_by(Collection.name)
        if not include_archived:
            stmt = stmt.where(Collection.archived_at.is_(None))
        result = await session.execute(stmt)
        return [c.to_dict() for c in result.scalars().all()]


async def get_collection(name: str) -> dict | None:
    async with async_session() as session:
        c = await session.get(Collection, name)
        return c.to_dict() if c else None


async def create_collection(data: dict) -> dict:
    async with async_session() as session:
        c = Collection(**{k: v for k, v in data.items() if hasattr(Collection, k)})
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c.to_dict()


async def update_collection(name: str, updates: dict) -> dict | None:
    allowed = {
        "description", "strategy", "sensitivity", "scope",
        "graph_enabled", "ai_summary_enabled", "ai_summary_threshold",
        "contact_name", "contact_email", "prompt_template",
        "system_prompt", "source_type", "source_url", "source_config_json",
    }
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return None
        for key, value in updates.items():
            if key in allowed and hasattr(c, key):
                setattr(c, key, value)
        await session.commit()
        await session.refresh(c)
        return c.to_dict()


async def delete_collection(name: str) -> bool:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return False
        await session.delete(c)
        await session.commit()
        return True


async def archive_collection(name: str) -> dict | None:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return None
        c.archived_at = utcnow()
        await session.commit()
        await session.refresh(c)
        return c.to_dict()


async def unarchive_collection(name: str) -> dict | None:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return None
        c.archived_at = None
        await session.commit()
        await session.refresh(c)
        return c.to_dict()


async def is_archived(name: str) -> bool:
    async with async_session() as session:
        c = await session.get(Collection, name)
        return bool(c and c.archived_at is not None)


async def purge_collection(name: str) -> dict:
    """Hard delete: OpenRAG partition + source files on disk + all DB rows.

    The collection must already be archived. Returns a report with the counts
    of rows/files removed and whether OpenRAG acknowledged the partition drop.
    """
    from app.services.openrag_client import OpenRAGClient

    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return {"status": "not_found"}
        if c.archived_at is None:
            return {"status": "not_archived"}

    # 1. OpenRAG partition
    openrag_status = "skipped"
    try:
        result = await OpenRAGClient(timeout=15.0).delete_partition(name)
        openrag_status = result.get("status", "unknown")
    except Exception as e:
        logger.warning("purge: failed to drop OpenRAG partition %s: %s", name, e)
        openrag_status = f"error: {e.__class__.__name__}"

    # 2. Source files on disk
    files_deleted = 0
    async with async_session() as session:
        paths_rows = await session.execute(
            select(SourceFile.storage_path).where(SourceFile.collection_name == name)
        )
        for (path,) in paths_rows:
            if not path:
                continue
            try:
                Path(path).unlink(missing_ok=True)
                files_deleted += 1
            except Exception as e:
                logger.warning("purge: failed to unlink %s: %s", path, e)

    # 3. DB cascade — one transaction
    counts: dict[str, int] = {}
    async with async_session() as session:
        for model in (
            SourceFile, EvalRun, EvalDataset, Feedback,
            IngestJob, PublicationHistory, Publication,
        ):
            stmt = delete(model).where(model.collection_name == name)
            result = await session.execute(stmt)
            counts[model.__tablename__] = result.rowcount or 0
        # finally the collection row itself
        c = await session.get(Collection, name)
        if c:
            await session.delete(c)
            counts["collections"] = 1
        await session.commit()

    return {
        "status": "purged",
        "collection": name,
        "openrag": openrag_status,
        "files_deleted": files_deleted,
        "rows_deleted": counts,
    }


async def get_or_create_collection(name: str) -> dict:
    """Get a collection, creating a minimal one if it doesn't exist."""
    existing = await get_collection(name)
    if existing:
        return existing
    return await create_collection({"name": name})


async def get_system_prompt(name: str) -> str:
    async with async_session() as session:
        c = await session.get(Collection, name)
        return c.system_prompt if c else ""


async def update_system_prompt(name: str, prompt: str) -> dict | None:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return None
        c.system_prompt = prompt
        await session.commit()
        await session.refresh(c)
        return c.to_dict()
