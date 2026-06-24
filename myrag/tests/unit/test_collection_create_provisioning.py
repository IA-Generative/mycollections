"""Création de collection : créateur propriétaire, groupes lecteurs, check-name.

Verrouille le fix de Bug 1 :
- ``created_by`` + ``scope_groups`` persistés ;
- le créateur (non super-admin) voit/atteint sa collection immédiatement ;
- les membres d'un groupe autorisé la voient (accès dynamique) ;
- provisioning best-effort (groupes Keycloak + sync OpenRAG) appelé dans l'ordre,
  et jamais bloquant ;
- ``GET /api/collections/check-name`` autoritaire (base + partitions OpenRAG).
"""

import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user


CREATOR = CurrentUser(sub="creator-sub", username="creator", groups=["/myrag/unrelated"])
THIRD = CurrentUser(sub="third-sub", username="third", groups=["/myrag/other"])
READER = CurrentUser(sub="reader-sub", username="reader", groups=["/dir/legal"])


def _reset_collections_table():
    url = os.environ.get("DATABASE_URL", "")
    if "sqlite" not in url:
        return
    path = url.split("///")[-1]
    try:
        con = sqlite3.connect(path)
        con.execute("DELETE FROM collections")
        con.commit()
        con.close()
    except sqlite3.OperationalError:
        pass


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    import app.config
    monkeypatch.setattr(app.config.settings, "data_dir", str(tmp_path))
    from app.main import app
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        _reset_collections_table()
        yield app, client
    app.dependency_overrides.clear()


def _as(app, user: CurrentUser):
    app.dependency_overrides[current_user] = lambda: user


def _no_openrag(mock_cls, partitions=()):
    m = mock_cls.return_value
    m.create_partition = AsyncMock(return_value={})
    m.list_models = AsyncMock(return_value={
        "data": [{"id": f"openrag-{p}"} for p in partitions]
    })
    m.list_files = AsyncMock(return_value=[])
    return m


@patch("app.routers.collections.OpenRAGClient")
def test_createur_voit_sa_collection_et_groupe_autorise_aussi(mock_cls, app_client):
    app, client = app_client
    _no_openrag(mock_cls)

    _as(app, CREATOR)
    resp = client.post("/api/collections", json={
        "name": "victor", "scope": "group", "scope_groups": ["/dir/legal"],
    })
    assert resp.status_code == 200, resp.text

    # Le créateur voit sa collection (via created_by, sans appartenir au groupe).
    names = {c["name"] for c in client.get("/api/collections").json()["collections"]}
    assert "victor" in names
    # Et il y accède directement, avec scope_groups persisté.
    fiche = client.get("/api/collections/victor").json()
    assert fiche["created_by"] == "creator-sub"
    assert fiche["scope_groups"] == ["/dir/legal"]

    # Un membre du groupe autorisé la voit aussi (accès dynamique).
    _as(app, READER)
    assert "victor" in {c["name"] for c in client.get("/api/collections").json()["collections"]}

    # Un tiers ne la voit pas, et n'y accède pas.
    _as(app, THIRD)
    assert "victor" not in {c["name"] for c in client.get("/api/collections").json()["collections"]}
    assert client.get("/api/collections/victor").status_code == 404


@patch("app.routers.collections.OpenRAGClient")
def test_check_name_autoritaire(mock_cls, app_client):
    app, client = app_client
    # "occupee" existe comme partition OpenRAG (orpheline, pas en base)
    _no_openrag(mock_cls, partitions=["occupee"])

    _as(app, CREATOR)
    client.post("/api/collections", json={"name": "victor"})

    # déjà en base
    assert client.get("/api/collections/check-name", params={"name": "victor"}).json() == {
        "available": False, "reason": "db"}
    # partition OpenRAG seulement
    assert client.get("/api/collections/check-name", params={"name": "occupee"}).json() == {
        "available": False, "reason": "partition"}
    # libre
    assert client.get("/api/collections/check-name", params={"name": "tout-neuf"}).json() == {
        "available": True}


@patch("app.routers.collections.SyncService")
@patch("app.routers.collections.KeycloakClient")
@patch("app.routers.collections.OpenRAGClient")
def test_provisioning_appele_dans_l_ordre(mock_or, mock_kc, mock_sync, app_client, monkeypatch):
    import app.config
    # Active le provisioning (sinon sauté en l'absence d'identifiants Keycloak).
    monkeypatch.setattr(app.config.settings, "keycloak_admin_password", "x")

    app, client = app_client
    _no_openrag(mock_or)
    kc = mock_kc.return_value
    kc.create_collection_groups = AsyncMock(return_value={
        "user_group_id": "ug", "admin_group_id": "ag",
        "user_group_path": "/myrag/victor", "admin_group_path": "/myrag/victor-admin",
    })
    kc.add_user_to_group = AsyncMock()
    sync = mock_sync.return_value
    sync.sync_collection = AsyncMock(return_value={"synced": 1, "errors": 0})

    _as(app, CREATOR)
    resp = client.post("/api/collections", json={
        "name": "victor", "scope_groups": ["/dir/legal"],
    })
    assert resp.status_code == 200

    kc.create_collection_groups.assert_awaited_once_with("victor")
    kc.add_user_to_group.assert_awaited_once_with("creator-sub", "ag")
    sync.sync_collection.assert_awaited_once()
    kwargs = sync.sync_collection.await_args.kwargs
    assert kwargs.get("reader_group_paths") == ["/dir/legal"]


@patch("app.routers.collections.SyncService")
@patch("app.routers.collections.KeycloakClient")
@patch("app.routers.collections.OpenRAGClient")
def test_provisioning_echoue_creation_ok(mock_or, mock_kc, mock_sync, app_client, monkeypatch):
    import app.config
    monkeypatch.setattr(app.config.settings, "keycloak_admin_password", "x")

    app, client = app_client
    _no_openrag(mock_or)
    mock_kc.return_value.create_collection_groups = AsyncMock(side_effect=Exception("KC down"))

    _as(app, CREATOR)
    # Le provisioning échoue mais la création reste OK (best-effort).
    resp = client.post("/api/collections", json={"name": "victor"})
    assert resp.status_code == 200
    assert "victor" in {c["name"] for c in client.get("/api/collections").json()["collections"]}
