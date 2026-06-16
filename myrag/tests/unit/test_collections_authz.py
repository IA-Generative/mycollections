"""Tests d'autorisation des endpoints collections (filtrage par groupe).

Reproduit et verrouille le bug signalé : auditeur1 ne doit pas voir/atteindre
les collections d'un autre groupe (user1).
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user


# Identités de test (groupes Keycloak)
SUPERADMIN = CurrentUser(sub="op", username="op", groups=["/myrag/superadmin"])
USER1 = CurrentUser(sub="u1", username="user1", groups=["/myrag/authzt-u1-admin"])
AUDITEUR1 = CurrentUser(sub="a1", username="auditeur1", groups=["/myrag/authzt-aud-admin"])


def _reset_collections_table():
    """Vide la table collections du fichier SQLite partagé entre modules de test.

    La suite partage un unique fichier DB via DATABASE_URL et tous les modules
    n'initialisent pas la base de la même façon : on isole donc explicitement ce
    test de toute pollution inter-modules (sinon l'override d'identité d'un autre
    test ou des collections résiduelles faussent le filtrage par groupe).
    """
    import os
    import sqlite3

    url = os.environ.get("DATABASE_URL", "")
    if "sqlite" not in url:
        return
    path = url.split("///")[-1]  # sqlite+aiosqlite:////tmp/x.db -> /tmp/x.db
    try:
        con = sqlite3.connect(path)
        con.execute("DELETE FROM collections")
        con.commit()
        con.close()
    except sqlite3.OperationalError:
        pass  # table pas encore créée : rien à nettoyer


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    import app.config
    monkeypatch.setattr(app.config.settings, "data_dir", str(tmp_path))
    from app.main import app
    # Pas d'override d'identité hérité d'un autre test.
    app.dependency_overrides.clear()
    # Le context manager déclenche le lifespan (init_db crée les tables).
    with TestClient(app) as client:
        _reset_collections_table()  # ardoise propre, indépendante des autres modules
        yield app, client
    app.dependency_overrides.clear()


def _as(app, user: CurrentUser):
    app.dependency_overrides[current_user] = lambda: user


def _no_openrag(mock_cls):
    """Neutralise les appels réseau OpenRAG du endpoint list/create."""
    m = mock_cls.return_value
    m.create_partition = AsyncMock(return_value={})
    m.list_models = AsyncMock(return_value={"data": []})
    m.list_files = AsyncMock(return_value=[])
    return m


@patch("app.routers.collections.OpenRAGClient")
def test_auditeur_ne_voit_pas_les_collections_de_user1(mock_cls, app_client):
    app, client = app_client
    _no_openrag(mock_cls)

    # Seed : superadmin crée deux collections de groupes différents
    _as(app, SUPERADMIN)
    assert client.post("/api/collections", json={"name": "authzt-u1"}).status_code == 200
    assert client.post("/api/collections", json={"name": "authzt-aud"}).status_code == 200

    # auditeur1 ne doit voir QUE authzt-aud
    _as(app, AUDITEUR1)
    names = {c["name"] for c in client.get("/api/collections").json()["collections"]}
    assert names == {"authzt-aud"}
    assert "authzt-u1" not in names

    # user1 ne doit voir QUE authzt-u1
    _as(app, USER1)
    names = {c["name"] for c in client.get("/api/collections").json()["collections"]}
    assert names == {"authzt-u1"}

    # superadmin voit tout (au moins les deux créées)
    _as(app, SUPERADMIN)
    names = {c["name"] for c in client.get("/api/collections").json()["collections"]}
    assert {"authzt-u1", "authzt-aud"} <= names


@patch("app.routers.collections.OpenRAGClient")
def test_acces_direct_a_une_collection_d_autrui_refuse(mock_cls, app_client):
    app, client = app_client
    _no_openrag(mock_cls)

    _as(app, SUPERADMIN)
    client.post("/api/collections", json={"name": "authzt-u1"})

    _as(app, AUDITEUR1)
    # GET direct : 404 (ne pas divulguer l'existence)
    assert client.get("/api/collections/authzt-u1").status_code == 404
    # PATCH : 403
    assert client.patch("/api/collections/authzt-u1", json={"description": "x"}).status_code == 403
    # system-prompt en lecture : 404 ; en écriture : 403
    assert client.get("/api/collections/authzt-u1/system-prompt").status_code == 404
    assert client.patch("/api/collections/authzt-u1/system-prompt",
                        json={"system_prompt": "x"}).status_code == 403

    app.dependency_overrides.clear()


@patch("app.routers.collections.OpenRAGClient")
def test_tout_utilisateur_authentifie_peut_creer(mock_cls, app_client):
    # Créer sa collection est une action utilisateur (multi-tenant), pas réservée
    # aux opérateurs. Seule l'administration (sync/jobs) reste superadmin-only.
    app, client = app_client
    _no_openrag(mock_cls)

    membre = CurrentUser(sub="m", username="m", groups=["/myrag/authzt-u1"])  # membre simple
    _as(app, membre)
    assert client.post("/api/collections", json={"name": "authzt-nouvelle"}).status_code == 200

    app.dependency_overrides.clear()
