"""Publication router — publish/unpublish collections to Open WebUI."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser, current_user
from app.database import async_session
from app.models.db import Collection, Publication, PublicationHistory, utcnow
from app.services import collectif_store, etats
from app.services.collection_store import get_or_create_collection
from app.services.nommage import titre_de

MESSAGE_VERIFICATION = (
    "Cette collection est en cours de vérification : elle ne peut être partagée qu'avec "
    "son groupe. Publier à tous demande qu'elle soit d'abord « publiée à tous » dans son "
    "circuit de contrôle."
)

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
async def publish_collection(name: str, req: PublishRequest, user: CurrentUser = Depends(current_user)):
    # Auto-create collection config if it doesn't exist
    await get_or_create_collection(name)

    now = utcnow()

    async with async_session() as session:
        # Règle 3 : une collection qui n'est pas « publiée à tous » n'est jamais servie
        # hors de son groupe. Un brouillon peut tout dire, il ne sert rien.
        col = await session.get(Collection, name)
        etat_collab = (col.etat_collab if col else None) or "amorcee"
        mention = etats.mention_verification(etat_collab)
        if mention and req.visibility == "all" and req.state != "draft":
            raise HTTPException(status_code=422, detail=MESSAGE_VERIFICATION)

        pub = await session.get(Publication, name)
        if not pub:
            pub = Publication(collection_name=name)
            session.add(pub)

        pub.state = req.state if req.state == "draft" else "published"
        pub.alias_enabled = req.alias_enabled
        # Le nom de la fiche dans l'assistant : celui qu'on saisit, sinon le TITRE de la
        # collection — plus jamais l'identifiant précédé d'un pictogramme.
        # N'est GARDÉ que s'il diffère du titre : sinon un titre corrigé plus tard
        # n'atteindrait jamais la fiche (fiche_assistant.nom_de_fiche retombe sur le titre).
        titre = titre_de(col.to_dict() if col else {"name": name})
        saisi = req.alias_name.strip()
        pub.alias_name = "" if saisi == titre else saisi
        pub.alias_description = req.alias_description.strip()
        pub.tool_enabled = req.tool_enabled
        pub.embed_enabled = req.embed_enabled
        pub.visibility = req.visibility
        pub.visibility_groups_json = json.dumps(req.visibility_groups)
        pub.widget_enabled = req.widget_enabled
        pub.browser_enabled = req.browser_enabled
        pub.published_at = now
        # L'identité vient du jeton, jamais du client (le champ reste accepté pour le wizard).
        pub.published_by = user.username or user.sub or req.published_by or "admin"

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
            from app.services.owui_client import OwuiAdminUnavailable
            from app.services.fiche_assistant import synchroniser_fiche
            # Tout ce qui part au socle se décide à UN endroit (nom = titre, étiquette =
            # catégorie, portée, mention de vérification) : la resynchronisation l'appelle
            # aussi. La fiche RECOUVRE le modèle `openrag-<col>` reçu de la connexion
            # OpenRAG — `base_model_id` absent, cf. owui_client.upsert_model.
            owui_result = await synchroniser_fiche(name)
        except OwuiAdminUnavailable as e:
            owui_error = str(e)
        except PermissionError as e:
            owui_error = str(e)
        except Exception as e:
            owui_error = f"Publication OWUI echouee : {e}"

    await collectif_store.consigner(
        "collection", name, "publication.publiee" if pub.state == "published" else "publication.brouillon",
        user.sub, collection_name=name,
        detail={"visibility": pub.visibility, "alias": pub.alias_enabled, "owui": owui_result is not None},
    )
    result = pub.to_dict()
    result["mention"] = mention
    result["nom_fiche"] = (owui_result or {}).get("nom") or pub.alias_name or titre
    result["owui"] = {
        "synced": owui_result is not None,
        "error": owui_error,
        "model_id": f"openrag-{name}" if owui_result else None,
    }
    return result


async def _retirer_du_socle(name: str) -> str | None:
    """Retire le modèle publié dans Open WebUI. Best-effort : rend le motif d'échec.

    Sans ce retrait, dépublier ne dépubliait rien du côté de l'assistant : l'alias
    restait offert aux utilisateurs, pointant une collection désormais vide — ou
    effacée. Le seul symptôme visible était une réponse vide.
    """
    try:
        from app.services.owui_client import OwuiClient, OwuiAdminUnavailable
        try:
            client = OwuiClient()
        except OwuiAdminUnavailable as e:
            return str(e)
        await client.delete_model(f"openrag-{name}")
        return None
    except Exception as e:  # noqa: BLE001 — le retrait ne doit jamais bloquer l'appelant
        return f"Retrait du socle echoue : {e}"


@router.post("/{name}/unpublish")
async def unpublish_collection(name: str, user: CurrentUser = Depends(current_user)):
    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            raise HTTPException(status_code=404, detail=f"No publication for '{name}'")
        pub.state = "disabled"

        session.add(PublicationHistory(
            collection_name=name, action="disabled", acted_by="admin",
        ))
        await session.commit()

    erreur = await _retirer_du_socle(name)
    await collectif_store.consigner("collection", name, "publication.retiree", user.sub, collection_name=name,
                                    detail={"owui_retire": erreur is None})
    return {"state": "disabled", "collection": name,
            "owui": {"removed": erreur is None, "error": erreur}}


@router.post("/{name}/archive")
async def archive_collection(name: str, user: CurrentUser = Depends(current_user)):
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

    await collectif_store.consigner("collection", name, "collection.archivee", user.sub, collection_name=name)
    return {
        "collection": name,
        "archived_at": result["archived_at"],
        "state": pub_state or "archived",
    }


@router.post("/{name}/unarchive")
async def unarchive_collection_endpoint(name: str, user: CurrentUser = Depends(current_user)):
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

    await collectif_store.consigner("collection", name, "collection.desarchivee", user.sub, collection_name=name)
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
