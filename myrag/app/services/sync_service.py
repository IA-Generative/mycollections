"""Sync service — synchronize Keycloak groups to OpenRAG memberships."""

import logging

from app.services.keycloak_client import KeycloakClient
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.sync")


class SyncService:
    def __init__(
        self,
        keycloak_client: KeycloakClient | None = None,
        openrag_client: OpenRAGClient | None = None,
    ):
        self.kc = keycloak_client or KeycloakClient()
        self.openrag = openrag_client or OpenRAGClient()

    @staticmethod
    def _map_group_to_role(group_name: str) -> str:
        """Map a Keycloak group name to an OpenRAG role."""
        if group_name == "superadmin":
            return "superadmin"
        if group_name.endswith("-admin"):
            return "owner"
        return "editor"

    async def sync_collection(
        self,
        collection: str,
        user_group_id: str,
        admin_group_id: str | None = None,
        reader_group_paths: list[str] | None = None,
    ) -> dict:
        """Sync a single collection's groups to OpenRAG memberships.

        ``user_group_id`` (membres → ``editor``) et ``admin_group_id`` (→ ``owner``)
        sont les 2 groupes ``/myrag/<name>[-admin]``. ``reader_group_paths`` est la
        liste des **groupes externes autorisés** à interroger (``scope_groups``),
        provisionnés aussi en ``editor``.
        """
        synced = 0
        errors = 0
        error_details: list[str] = []

        def _fail(msg: str) -> None:
            """Enregistre une erreur : log + compteur + détail remonté à l'appelant."""
            nonlocal errors
            errors += 1
            logger.warning("sync[%s] %s", collection, msg)
            error_details.append(msg)

        # Ensure partition exists
        try:
            await self.openrag.create_partition(collection)
        except Exception as e:
            # Échec dur : sans partition, rien ne peut être synchronisé.
            _fail(f"create_partition a échoué: {e}")
            return {"collection": collection, "synced": 0, "errors": errors,
                    "error_details": error_details}

        # Get existing OpenRAG users
        try:
            or_users = await self.openrag._get("/users/")
            or_users_list = or_users.get("users", []) if isinstance(or_users, dict) else or_users
            or_by_ext_id = {
                u.get("external_user_id"): u
                for u in or_users_list
                if u.get("external_user_id")
            }
        except Exception as e:
            # Échec probable d'auth OpenRAG (token admin) — rendu visible.
            _fail(f"liste des utilisateurs OpenRAG impossible (token admin ?): {e}")
            or_by_ext_id = {}

        async def _resolve_or_user(member: dict) -> dict | None:
            """Renvoie l'utilisateur OpenRAG (le crée si absent), ou None sur échec."""
            kc_id = member["id"]
            or_user = or_by_ext_id.get(kc_id)
            if or_user:
                return or_user
            username = member.get("username", "")
            try:
                display = (
                    f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
                    or username
                )
                or_user = await self.openrag._post(
                    "/users/",
                    json={"display_name": display, "external_user_id": kc_id, "is_admin": False},
                )
                or_by_ext_id[kc_id] = or_user
                return or_user
            except Exception as e:
                _fail(f"création de l'utilisateur {username} échouée: {e}")
                return None

        async def _provision_members(group_id: str, role: str, *, create_if_missing: bool) -> None:
            """Ajoute les membres d'un groupe Keycloak à la partition avec ``role``."""
            nonlocal synced
            try:
                members = await self.kc.list_group_members(group_id)
            except Exception as e:
                _fail(f"liste des membres du groupe Keycloak ({role}) impossible (droits admin ?): {e}")
                return
            for member in members:
                username = member.get("username", "")
                if username.startswith("service-account-"):
                    continue
                if create_if_missing:
                    or_user = await _resolve_or_user(member)
                else:
                    or_user = or_by_ext_id.get(member["id"])
                if not (or_user and or_user.get("id")):
                    continue
                try:
                    await self.openrag._upload_form(
                        f"/partition/{collection}/users",
                        data={"user_id": str(or_user["id"]), "role": role},
                    )
                    synced += 1
                except Exception as e:
                    # _upload_form renvoie {"status":"exists"} sur 409 sans lever :
                    # une exception ici est donc une vraie erreur (champ/endpoint/auth).
                    _fail(f"ajout de {username} ({role}) à la partition échoué: {e}")

        # Membres du groupe lecteur /myrag/<name> → editor
        await _provision_members(user_group_id, "editor", create_if_missing=True)

        # Membres du groupe gestionnaire /myrag/<name>-admin → owner
        if admin_group_id:
            # owner sans (re)création : les owners doivent aussi être membres du
            # groupe utilisateur (déjà créés ci-dessus) — conserve le comportement.
            await _provision_members(admin_group_id, "owner", create_if_missing=False)

        # Groupes externes autorisés (scope_groups) → editor
        for path in reader_group_paths or []:
            gid = await self.kc.get_group_id_by_path(path)
            if not gid:
                _fail(f"groupe lecteur introuvable: {path}")
                continue
            await _provision_members(gid, "editor", create_if_missing=True)

        result = {"collection": collection, "synced": synced, "errors": errors}
        if error_details:
            result["error_details"] = error_details
        return result

    async def sync_all(self) -> list[dict]:
        """Sync all MyRAG collection groups to OpenRAG."""
        try:
            collections = await self.kc.list_collection_groups()
        except Exception as e:
            # Cause racine typique : le client admin Keycloak (myrag-admin) n'a pas
            # les droits realm-management. On remonte une erreur explicite plutôt
            # qu'un 500 nu / un sync vide silencieux.
            logger.error("sync_all: lecture des groupes Keycloak impossible: %s", e)
            return [{"collection": "*", "synced": 0, "errors": 1,
                     "error": f"Keycloak admin inaccessible (droits du service account ?): {e}"}]
        results = []

        for col in collections:
            try:
                result = await self.sync_collection(
                    collection=col["collection"],
                    user_group_id=col["user_group_id"],
                    admin_group_id=col.get("admin_group_id"),
                )
                results.append(result)
                logger.info(f"Synced {col['collection']}: {result['synced']} members")
            except Exception as e:
                logger.error(f"Failed to sync {col['collection']}: {e}")
                results.append({
                    "collection": col["collection"],
                    "synced": 0,
                    "errors": 1,
                    "error": str(e),
                })

        return results
