"""Tests for sync service Keycloak ↔ OpenRAG (TDD)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.sync_service import SyncService


@pytest.fixture
def sync():
    return SyncService(
        keycloak_client=MagicMock(),
        openrag_client=MagicMock(),
    )


class TestSyncService:
    def test_init(self, sync):
        assert sync.kc is not None
        assert sync.openrag is not None

    def test_map_group_to_role_user(self, sync):
        assert sync._map_group_to_role("ceseda-v3") == "editor"

    def test_map_group_to_role_admin(self, sync):
        assert sync._map_group_to_role("ceseda-v3-admin") == "owner"

    def test_map_group_to_role_superadmin(self, sync):
        assert sync._map_group_to_role("superadmin") == "superadmin"

    @pytest.mark.asyncio
    async def test_sync_collection(self, sync):
        sync.kc.list_group_members = AsyncMock(return_value=[
            {"id": "kc-user-1", "username": "eric"},
            {"id": "kc-user-2", "username": "claire"},
        ])
        sync.openrag.create_partition = AsyncMock()
        sync.openrag._post = AsyncMock(return_value={"status": "ok"})
        sync.openrag._get = AsyncMock(return_value={"users": []})

        # Mock the upload form data for partition members
        sync.openrag._upload_form = AsyncMock(return_value={"status": "ok"})

        result = await sync.sync_collection(
            collection="ceseda-v3",
            user_group_id="ug-123",
            admin_group_id="ag-456",
        )
        assert result["collection"] == "ceseda-v3"
        assert result["synced"] >= 0

    @pytest.mark.asyncio
    async def test_sync_all(self, sync):
        sync.kc.list_collection_groups = AsyncMock(return_value=[
            {"collection": "ceseda-v3", "user_group_id": "ug-1", "admin_group_id": "ag-1"},
        ])
        sync.sync_collection = AsyncMock(return_value={"collection": "ceseda-v3", "synced": 2})

        results = await sync.sync_all()
        assert len(results) == 1
        assert results[0]["collection"] == "ceseda-v3"


class TestSyncErrorSurfacing:
    """Le fix : les échecs ne doivent plus être avalés silencieusement (synced=0 muet)."""

    @pytest.mark.asyncio
    async def test_keycloak_member_listing_failure_is_surfaced(self, sync):
        # Cause typique : service account sans droits realm-management -> 403.
        sync.openrag.create_partition = AsyncMock()
        sync.openrag._get = AsyncMock(return_value={"users": []})
        sync.kc.list_group_members = AsyncMock(side_effect=Exception("403 Forbidden"))

        result = await sync.sync_collection("ceseda-v3", user_group_id="ug-1")
        assert result["synced"] == 0
        assert result["errors"] >= 1
        assert result.get("error_details"), "l'erreur doit être remontée, pas avalée"
        assert any("403" in d or "Keycloak" in d for d in result["error_details"])

    @pytest.mark.asyncio
    async def test_partition_membership_failure_is_counted(self, sync):
        sync.openrag.create_partition = AsyncMock()
        sync.openrag._get = AsyncMock(return_value={"users": [{"external_user_id": "u1", "id": "or1"}]})
        sync.kc.list_group_members = AsyncMock(return_value=[{"id": "u1", "username": "eric"}])
        sync.openrag._upload_form = AsyncMock(side_effect=Exception("400 bad field"))

        result = await sync.sync_collection("ceseda-v3", user_group_id="ug-1")
        assert result["synced"] == 0
        assert result["errors"] >= 1
        assert any("editor" in d for d in result.get("error_details", []))

    @pytest.mark.asyncio
    async def test_create_partition_failure_stops_early(self, sync):
        sync.openrag.create_partition = AsyncMock(side_effect=Exception("401 Unauthorized"))

        result = await sync.sync_collection("ceseda-v3", user_group_id="ug-1")
        assert result["synced"] == 0
        assert result["errors"] >= 1
        assert any("create_partition" in d for d in result.get("error_details", []))

    @pytest.mark.asyncio
    async def test_sync_all_surfaces_keycloak_group_failure(self, sync):
        # Si on ne peut même pas lister les groupes, on remonte une erreur claire.
        sync.kc.list_collection_groups = AsyncMock(side_effect=Exception("403 groups"))

        results = await sync.sync_all()
        assert len(results) == 1
        assert results[0]["errors"] == 1
        assert "error" in results[0] and "403" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_happy_path_has_no_errors(self, sync):
        sync.openrag.create_partition = AsyncMock()
        sync.openrag._get = AsyncMock(return_value={"users": [{"external_user_id": "u1", "id": "or1"}]})
        sync.kc.list_group_members = AsyncMock(return_value=[{"id": "u1", "username": "eric"}])
        sync.openrag._upload_form = AsyncMock(return_value={"status": "ok"})

        result = await sync.sync_collection("ceseda-v3", user_group_id="ug-1")
        assert result["synced"] == 1
        assert result["errors"] == 0
        assert "error_details" not in result
