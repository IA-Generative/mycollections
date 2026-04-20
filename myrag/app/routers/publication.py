"""Publication router — publish/unpublish collections to Open WebUI."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import async_session
from app.models.db import Publication, PublicationHistory, utcnow
from app.services.collection_store import get_or_create_collection

router = APIRouter(prefix="/api/collections", tags=["Publication"])


class PublishRequest(BaseModel):
    alias_enabled: bool = True
    alias_name: str = ""
    alias_description: str = ""
    tool_enabled: bool = False
    embed_enabled: bool = False
    visibility: str = "all"
    visibility_groups: list[str] = []
    widget_enabled: bool = False
    browser_enabled: bool = False
    published_by: str = ""
    state: str = ""  # allow "draft" for save-as-draft


@router.get("/{name}/publication")
async def get_publication_status(name: str):
    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            return {"collection": name, "state": "draft"}
        return pub.to_dict()


@router.post("/{name}/publish")
async def publish_collection(name: str, req: PublishRequest):
    # Auto-create collection config if it doesn't exist
    await get_or_create_collection(name)

    now = utcnow()

    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            pub = Publication(collection_name=name)
            session.add(pub)

        pub.state = req.state if req.state == "draft" else "published"
        pub.alias_enabled = req.alias_enabled
        pub.alias_name = req.alias_name or f"📚 {name}"
        pub.tool_enabled = req.tool_enabled
        pub.embed_enabled = req.embed_enabled
        pub.visibility = req.visibility
        pub.visibility_groups_json = json.dumps(req.visibility_groups)
        pub.widget_enabled = req.widget_enabled
        pub.browser_enabled = req.browser_enabled
        pub.published_at = now
        pub.published_by = req.published_by or "admin"

        # History entry
        history = PublicationHistory(
            collection_name=name,
            action=pub.state,
            acted_by=pub.published_by,
            acted_at=now,
            details_json=json.dumps({
                "alias": pub.alias_enabled,
                "tool": pub.tool_enabled,
                "embed": pub.embed_enabled,
                "visibility": pub.visibility,
            }),
        )
        session.add(history)

        await session.commit()
        await session.refresh(pub)

    # --- OWUI model registration ---------------------------------------
    # The publish flow here is two-step: we always persist local state
    # first (done above), then best-effort-sync to OWUI. A broken OWUI
    # sync should not roll back the local state — the user can re-run the
    # publish to retry, and the UI surfaces the error.
    owui_result: dict | None = None
    owui_error: str | None = None
    if req.alias_enabled and pub.state == "published":
        try:
            from app.services.owui_client import OwuiClient, OwuiAdminUnavailable
            client = OwuiClient()
            # Access control: map visibility_groups (Keycloak group names)
            # onto OWUI's read/write group_ids. V1 passes names through as-is;
            # if OWUI uses sub-based group ids, the group list silently matches
            # nothing (the model stays restricted, not public). Fine for V1,
            # to revisit when we wire KC group id resolution.
            ac = None
            if req.visibility == "group" and req.visibility_groups:
                ac = {
                    "read":  {"group_ids": req.visibility_groups, "user_ids": []},
                    "write": {"group_ids": req.visibility_groups, "user_ids": []},
                }
            # Route through the pipelines container's openrag manifold
            # (id "openrag.<col>") rather than the direct OpenRAG provider
            # ("openrag-<col>"). The pipeline appends source links to the
            # response — the direct provider can't because OWUI ignores
            # OpenRAG's non-standard `extra` field.
            owui_result = await client.upsert_model(
                model_id=f"openrag-{name}",
                name=pub.alias_name,
                description=req.alias_description,
                base_model_id=f"openrag.{name}",
                access_control=ac,
            )
        except OwuiAdminUnavailable as e:
            owui_error = str(e)
        except PermissionError as e:
            owui_error = str(e)
        except Exception as e:
            owui_error = f"Publication OWUI echouee : {e}"

    result = pub.to_dict()
    result["owui"] = {
        "synced": owui_result is not None,
        "error": owui_error,
        "model_id": f"openrag-{name}" if owui_result else None,
    }
    return result


@router.post("/{name}/unpublish")
async def unpublish_collection(name: str):
    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            raise HTTPException(status_code=404, detail=f"No publication for '{name}'")
        pub.state = "disabled"

        session.add(PublicationHistory(
            collection_name=name, action="disabled", acted_by="admin",
        ))
        await session.commit()
        return {"state": pub.state, "collection": name}


@router.post("/{name}/archive")
async def archive_collection(name: str):
    """Archive a collection: hide it from the default catalog and disable any
    active publication. Reversible via /unarchive. Data is retained.
    """
    from app.services.collection_store import archive_collection as store_archive

    result = await store_archive(name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    async with async_session() as session:
        pub = await session.get(Publication, name)
        pub_state = None
        if pub:
            pub.state = "archived"
            pub_state = pub.state
        session.add(PublicationHistory(
            collection_name=name, action="archived", acted_by="admin",
        ))
        await session.commit()

    return {
        "collection": name,
        "archived_at": result["archived_at"],
        "state": pub_state or "archived",
    }


@router.post("/{name}/unarchive")
async def unarchive_collection_endpoint(name: str):
    """Restore an archived collection. Publication state is NOT auto-restored:
    the admin must re-publish explicitly if needed.
    """
    from app.services.collection_store import unarchive_collection as store_unarchive

    result = await store_unarchive(name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    async with async_session() as session:
        pub = await session.get(Publication, name)
        if pub and pub.state == "archived":
            pub.state = "disabled"
        session.add(PublicationHistory(
            collection_name=name, action="unarchived", acted_by="admin",
        ))
        await session.commit()

    return {"collection": name, "archived_at": None}


@router.get("/{name}/publication/history")
async def publication_history(name: str):
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(PublicationHistory)
            .where(PublicationHistory.collection_name == name)
            .order_by(PublicationHistory.acted_at.desc())
        )
        entries = result.scalars().all()
        return {
            "collection": name,
            "history": [
                {"action": h.action, "at": h.acted_at.isoformat(), "by": h.acted_by,
                 "details": json.loads(h.details_json or "{}")}
                for h in entries
            ],
        }
