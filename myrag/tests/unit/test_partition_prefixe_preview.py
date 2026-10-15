"""Preview : une preview partage l'OpenRAG de la bêta — elle ne touche qu'aux partitions de son préfixe."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services import nommage
from app.services.openrag_client import OpenRAGClient, PartitionHorsPerimetre


@pytest.fixture
def preview(monkeypatch):
    monkeypatch.setattr(settings, "partition_prefixe", "pr-12-")


@pytest.fixture
def client():
    return OpenRAGClient(base_url="http://openrag:8080", admin_token="or-test-token")


def _http_qui_repond():
    reponse = MagicMock(status_code=200, content=b"{}", json=MagicMock(return_value={}))
    reponse.raise_for_status = MagicMock()
    http = MagicMock()
    for verbe in ("get", "post", "delete"):
        setattr(http, verbe, AsyncMock(return_value=reponse))
    contexte = MagicMock()
    contexte.__aenter__ = AsyncMock(return_value=http)
    contexte.__aexit__ = AsyncMock(return_value=False)
    return contexte, http


@pytest.mark.asyncio
async def test_hors_preview_rien_ne_change(client):
    contexte, http = _http_qui_repond()
    with patch("app.services.openrag_client.httpx.AsyncClient", return_value=contexte):
        await client.create_partition("codes-natinf")
    http.post.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "appel",
    [
        lambda c: c.create_partition("codes-natinf"),
        lambda c: c.delete_partition("codes-natinf"),
        lambda c: c.list_files("codes-natinf"),
        lambda c: c.file_detail("codes-natinf", "f1"),
        lambda c: c.upload_chunk("codes-natinf", {"content": "x"}),
        lambda c: c.search("codes-natinf", "q"),
        lambda c: c.search(["pr-12-a", "codes-natinf"], "q"),
        lambda c: c.chat("openrag-codes-natinf", []),
        lambda c: c.chat("openrag-all", []),
        lambda c: c._upload_form("/partition/codes-natinf/users", {"user_id": "1"}),
        lambda c: c.create_partition("pr-12-"),
    ],
)
async def test_en_preview_une_partition_de_la_beta_est_refusee_sans_appel(preview, client, appel):
    contexte, http = _http_qui_repond()
    with patch("app.services.openrag_client.httpx.AsyncClient", return_value=contexte):
        with pytest.raises(PartitionHorsPerimetre):
            await appel(client)
    http.get.assert_not_called()
    http.post.assert_not_called()
    http.delete.assert_not_called()


@pytest.mark.asyncio
async def test_en_preview_une_partition_du_prefixe_passe(preview, client):
    contexte, http = _http_qui_repond()
    with patch("app.services.openrag_client.httpx.AsyncClient", return_value=contexte):
        await client.create_partition("pr-12-codes-natinf")
        await client.search(["pr-12-a", "pr-12-b"], "q")
        await client.chat("openrag-pr-12-a", [])
    assert http.post.call_count == 2 and http.get.call_count == 1


def test_le_nommage_impose_le_prefixe_en_preview(preview):
    assert nommage.motif_de_refus("codes-natinf") == "preview"
    assert nommage.motif_de_refus("pr-12-codes-natinf") is None
    assert nommage.regles()["prefixe_impose"] == "pr-12-"


def test_hors_preview_le_nommage_ne_change_pas():
    assert nommage.motif_de_refus("codes-natinf") is None
    assert nommage.regles()["prefixe_impose"] == ""


def test_adresse_interne_du_sso_pour_le_serveur_seulement(monkeypatch):
    from app import auth

    monkeypatch.setattr(settings, "keycloak_url", "https://sso.fake-domain.name")
    monkeypatch.setattr(settings, "keycloak_realm", "preview")
    monkeypatch.setattr(settings, "keycloak_internal_url", "")
    assert auth._jwks_uri() == "https://sso.fake-domain.name/realms/preview/protocol/openid-connect/certs"
    monkeypatch.setattr(settings, "keycloak_internal_url", "http://keycloak.sso.svc:8080/")
    assert auth._jwks_uri() == "http://keycloak.sso.svc:8080/realms/preview/protocol/openid-connect/certs"
    assert auth._issuer() == "https://sso.fake-domain.name/realms/preview"
