"""Collections router — CRUD for MyRAG collections + prompt templates."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.auth import CurrentUser, current_user
from app.services import access
from app.services.keycloak_client import KeycloakClient
from app.services.sync_service import SyncService
from app.models.collection import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPLATE_KEY,
    get_prompt_template,
    list_prompt_templates,
    save_custom_template,
    delete_custom_template,
)
from app.services.collection_store import (
    list_collections as db_list_collections,
    get_collection as db_get_collection,
    create_collection as db_create_collection,
    update_collection as db_update_collection,
    get_system_prompt as db_get_system_prompt,
    update_system_prompt as db_update_system_prompt,
    purge_collection as db_purge_collection,
)
from app.services.openrag_client import OpenRAGClient

log = logging.getLogger("myrag.collections")

router = APIRouter(prefix="/api/collections", tags=["Collections"])


def _provisioning_enabled() -> bool:
    """Vrai si Keycloak admin est configuré (sinon on saute le provisioning).

    En dev/tests sans identifiants Keycloak, la création reste fonctionnelle :
    seul l'accès via groupes/OpenRAG (best-effort) est ignoré.
    """
    return bool(settings.keycloak_client_secret or settings.keycloak_admin_password)


async def _provision_collection_access(
    name: str, creator_sub: str | None, reader_group_paths: list[str], openrag_client: OpenRAGClient
) -> None:
    """Best-effort : crée les 2 groupes Keycloak, fait du créateur un gestionnaire
    (groupe ``-admin`` → OpenRAG ``owner``) et provisionne les groupes lecteurs
    autorisés (→ OpenRAG ``editor``). Ne fait jamais échouer la création.
    """
    if not _provisioning_enabled():
        return
    try:
        kc = KeycloakClient()
        groups = await kc.create_collection_groups(name)
        admin_gid = groups.get("admin_group_id")
        user_gid = groups.get("user_group_id")
        if admin_gid and creator_sub:
            await kc.add_user_to_group(creator_sub, admin_gid)
        await SyncService(kc, openrag_client).sync_collection(
            name,
            user_group_id=user_gid,
            admin_group_id=admin_gid,
            reader_group_paths=reader_group_paths or [],
        )
    except Exception as e:
        log.warning("provisioning accès collection '%s' échoué (best-effort): %s", name, e)


# --- Request models ---

class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""
    strategy: str = "auto"
    sensitivity: str = "public"
    prompt_template: str = DEFAULT_TEMPLATE_KEY
    system_prompt: str | None = None
    graph_enabled: bool = False
    ai_summary_enabled: bool = False
    ai_summary_threshold: int = 1000
    scope: str = "group"
    scope_groups: list[str] = []
    contact_name: str = ""
    contact_email: str = ""


class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str


class CreateTemplateRequest(BaseModel):
    key: str
    name: str
    description: str = ""
    icon: str = "📄"
    prompt: str


# ============================================================
# Prompt templates catalog (MUST be before /{name} routes)
# ============================================================

@router.get("/templates", tags=["Prompt Templates"])
async def get_prompt_templates():
    return {"templates": list_prompt_templates()}


@router.get("/templates/{key}", tags=["Prompt Templates"])
async def get_prompt_template_detail(key: str):
    tpl = get_prompt_template(key)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{key}' not found")
    return {"key": key, **tpl}


@router.post("/templates", tags=["Prompt Templates"])
async def create_prompt_template(req: CreateTemplateRequest):
    existing = get_prompt_template(req.key)
    if existing and not existing.get("custom"):
        raise HTTPException(status_code=409, detail=f"Cannot overwrite builtin template '{req.key}'")
    save_custom_template(key=req.key, name=req.name, description=req.description, icon=req.icon, prompt=req.prompt)
    return {"status": "created", "key": req.key}


@router.put("/templates/{key}", tags=["Prompt Templates"])
async def update_prompt_template(key: str, req: CreateTemplateRequest):
    existing = get_prompt_template(key)
    if existing and not existing.get("custom"):
        raise HTTPException(status_code=403, detail=f"Cannot modify builtin template '{key}'")
    save_custom_template(key=key, name=req.name, description=req.description, icon=req.icon, prompt=req.prompt)
    return {"status": "updated", "key": key}


@router.delete("/templates/{key}", tags=["Prompt Templates"])
async def delete_prompt_template_endpoint(key: str):
    if not delete_custom_template(key):
        raise HTTPException(status_code=403, detail=f"Cannot delete builtin template '{key}'")
    return {"status": "deleted", "key": key}


# ============================================================
# Collection CRUD (backed by SQLite/PostgreSQL)
# ============================================================

@router.get("")
async def list_collections_endpoint(
    include_archived: bool = False,
    user: CurrentUser = Depends(current_user),
):
    """List the MyRAG collections visible to the caller.

    Visibility is derived from the caller's Keycloak groups (members of
    ``/myrag/<collection>[-admin]`` or ``/myrag/superadmin``). Merges DB
    collections with OpenRAG partitions. Archived collections are hidden by
    default; pass ?include_archived=true to include them.
    """
    allowed = access.visible_collection_names(user.groups)  # None = superadmin/all
    # Visibilité par fiche : dépend de scope / scope_groups / created_by, donc on
    # charge tout puis on filtre via access.can_read (plus un simple set de noms).
    all_cols = await db_list_collections(include_archived=include_archived)
    collections = [
        c for c in all_cols
        if access.can_read(
            name=c["name"], scope=c.get("scope"), scope_groups=c.get("scope_groups"),
            created_by=c.get("created_by"), user_groups=user.groups, user_sub=user.sub,
        )
    ]
    # Fetch the full set of known names (incl. archived) so we do not
    # re-surface an archived collection via the OpenRAG merge below.
    all_known = await db_list_collections(include_archived=True)
    known_names = {c["name"] for c in all_known}

    # Also fetch partitions from OpenRAG
    try:
        client = OpenRAGClient(timeout=10.0)
        models = await client.list_models()
        for m in models.get("data", []):
            model_id = m.get("id", "")
            if model_id.startswith("openrag-"):
                name = model_id[len("openrag-"):]
                if (name and name not in known_names and name not in ("all", "default")
                        and (allowed is None or name in allowed)):
                    # Orphan: a partition exists on OpenRAG but no MyRAG fiche
                    # was ever created for it. Flagged so the UI can surface
                    # "adoptable" cards without fabricating a description from
                    # raw filenames (which read as junk to end users).
                    collections.append({"name": name, "description": "", "strategy": "auto",
                                        "sensitivity": "public", "scope": "group",
                                        "orphan": True})
                    known_names.add(name)

        # Enrich with file counts
        for c in collections:
            try:
                files = await client.list_files(c["name"])
                c["file_count"] = len(files)
            except Exception:
                c["file_count"] = 0
    except Exception:
        pass

    return {"collections": collections}


@router.post("")
async def create_collection_endpoint(
    req: CreateCollectionRequest,
    user: CurrentUser = Depends(current_user),
):
    """Create a new collection (operators only: superadmin or a collection-admin)."""
    if not access.can_create_collection(user.groups):
        raise HTTPException(status_code=403, detail="Création réservée aux opérateurs")
    existing = await db_get_collection(req.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Collection '{req.name}' already exists")

    system_prompt = req.system_prompt
    if not system_prompt:
        tpl = get_prompt_template(req.prompt_template)
        system_prompt = tpl["prompt"] if tpl else DEFAULT_SYSTEM_PROMPT

    # Create partition in OpenRAG
    client = OpenRAGClient()
    try:
        await client.create_partition(req.name)
    except Exception:
        pass  # OpenRAG may not be reachable

    data = req.model_dump()
    data["system_prompt"] = system_prompt
    data["created_by"] = user.sub  # garantit l'accès du créateur à sa collection
    collection = await db_create_collection(data)

    # Provisionne l'accès (créateur gestionnaire + groupes lecteurs autorisés).
    # Best-effort : ne fait jamais échouer la création.
    await _provision_collection_access(req.name, user.sub, req.scope_groups, client)

    return {"status": "created", "collection": collection}


@router.get("/check-name")
async def check_name_endpoint(name: str, user: CurrentUser = Depends(current_user)):
    """Disponibilité **autoritaire** d'un nom de collection (avant /{name}).

    Teste la base complète (non filtrée par groupe) + les partitions OpenRAG :
    le namespace est global, donc on révèle uniquement « pris / libre » (pas le
    contenu) pour que la vérif du wizard colle à la contrainte d'unicité backend.
    """
    norm = name.strip().lower()
    if not norm:
        return {"available": False, "reason": "empty"}
    if await db_get_collection(norm):
        return {"available": False, "reason": "db"}
    try:
        models = await OpenRAGClient(timeout=10.0).list_models()
        for m in models.get("data", []):
            mid = m.get("id", "")
            if mid.startswith("openrag-") and mid[len("openrag-"):] == norm:
                return {"available": False, "reason": "partition"}
    except Exception:
        pass  # OpenRAG indisponible : on ne bloque pas sur ce critère
    return {"available": True}


@router.get("/{name}")
async def get_collection_endpoint(name: str, user: CurrentUser = Depends(current_user)):
    collection = await db_get_collection(name)
    # 404 (pas 403) si absent ou non lisible : ne pas divulguer l'existence.
    if not collection or not access.can_read(
        name=name, scope=collection.get("scope"), scope_groups=collection.get("scope_groups"),
        created_by=collection.get("created_by"), user_groups=user.groups, user_sub=user.sub,
    ):
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return collection


@router.patch("/{name}")
async def update_collection_endpoint(
    name: str, updates: dict, user: CurrentUser = Depends(current_user)
):
    existing = await db_get_collection(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    if not access.can_write(
        name=name, created_by=existing.get("created_by"),
        user_groups=user.groups, user_sub=user.sub,
    ):
        raise HTTPException(status_code=403, detail="Accès refusé à cette collection")
    collection = await db_update_collection(name, updates)
    return collection


@router.delete("/{name}")
async def purge_collection_endpoint(name: str, user: CurrentUser = Depends(current_user)):
    """Hard-delete a collection. Requires the collection to be archived first.

    Drops the OpenRAG partition, removes source files on disk, and cascades
    all related DB rows (publications, jobs, feedback, evals, source_files).
    """
    existing = await db_get_collection(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    if not access.can_write(
        name=name, created_by=existing.get("created_by"),
        user_groups=user.groups, user_sub=user.sub,
    ):
        raise HTTPException(status_code=403, detail="Accès refusé à cette collection")
    result = await db_purge_collection(name)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    if result["status"] == "not_archived":
        raise HTTPException(
            status_code=409,
            detail=f"Collection '{name}' must be archived before it can be purged",
        )
    return result


# --- System prompt ---

@router.get("/{name}/system-prompt")
async def get_system_prompt_endpoint(name: str, user: CurrentUser = Depends(current_user)):
    collection = await db_get_collection(name)
    if not collection:
        # Pas de fiche : on retombe sur le contrôle par groupe (orphelin/défaut).
        if not access.can_read_collection(name, user.groups):
            raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
        return {"collection": name, "system_prompt": DEFAULT_SYSTEM_PROMPT,
                "source": "default", "template": DEFAULT_TEMPLATE_KEY}
    if not access.can_read(
        name=name, scope=collection.get("scope"), scope_groups=collection.get("scope_groups"),
        created_by=collection.get("created_by"), user_groups=user.groups, user_sub=user.sub,
    ):
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return {
        "collection": name,
        "system_prompt": collection.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
        "source": "collection",
        "template": collection.get("prompt_template", DEFAULT_TEMPLATE_KEY),
    }


@router.patch("/{name}/system-prompt")
async def update_system_prompt_endpoint(
    name: str, req: UpdateSystemPromptRequest, user: CurrentUser = Depends(current_user)
):
    existing = await db_get_collection(name)
    if not access.can_write(
        name=name, created_by=(existing or {}).get("created_by"),
        user_groups=user.groups, user_sub=user.sub,
    ):
        raise HTTPException(status_code=403, detail="Accès refusé à cette collection")
    result = await db_update_system_prompt(name, req.system_prompt)
    if not result:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return {"status": "updated", "collection": name, "system_prompt": result.get("system_prompt")}
