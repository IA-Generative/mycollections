"""La fin d'une preview ne supprime que ses propres partitions, et rien hors preview."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services import nettoyage_preview

COLLECTIONS = [{"name": "pr-12-codes"}, {"name": "pr-12-guide"}, {"name": "codes-natinf"}]


@pytest.mark.asyncio
async def test_hors_preview_rien_n_est_supprime(monkeypatch):
    monkeypatch.setattr(settings, "partition_prefixe", "")
    with (
        patch.object(nettoyage_preview, "list_collections", AsyncMock(return_value=COLLECTIONS)),
        patch("app.services.openrag_client.OpenRAGClient.delete_partition", AsyncMock()) as suppr,
    ):
        assert await nettoyage_preview.nettoyer() == []
    suppr.assert_not_called()


@pytest.mark.asyncio
async def test_en_preview_seules_ses_partitions_partent(monkeypatch):
    monkeypatch.setattr(settings, "partition_prefixe", "pr-12-")
    with (
        patch.object(nettoyage_preview, "list_collections", AsyncMock(return_value=COLLECTIONS)),
        patch("app.services.openrag_client.OpenRAGClient.delete_partition", AsyncMock()) as suppr,
    ):
        assert await nettoyage_preview.nettoyer() == ["pr-12-codes", "pr-12-guide"]
    assert [c.args[0] for c in suppr.call_args_list] == ["pr-12-codes", "pr-12-guide"]
