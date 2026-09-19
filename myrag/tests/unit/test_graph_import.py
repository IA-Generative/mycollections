"""Import d'un graphe construit hors de MyRAG (PUT /graph/{collection})."""

import json

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user
from app.services.graph_builder import GraphBuilder, GraphImportError, graph_from_import


GESTIONNAIRE = CurrentUser(sub="g1", username="gest", groups=["/myrag/grimp-ceseda-admin"])
LECTEUR = CurrentUser(sub="l1", username="lecteur", groups=["/myrag/grimp-autre-admin"])
SUPERADMIN = CurrentUser(sub="op", username="op", groups=["/myrag/superadmin"])

GRAPHE = {
    "nodes": [
        {"id": "L423-1", "label": "Article L. 423-1", "livre": "IV", "content_preview": "L'étranger marié…"},
        {"id": "L423-3", "label": "Article L. 423-3", "livre": "IV", "referenced_by": ["FAUX"]},
        {"id": "Annexe 10"},
    ],
    "edges": [
        {"source": "L423-3", "target": "L423-1", "origine": "legi"},
        {"source": "Annexe 10", "target": "L423-1"},
        {"source": "L423-1", "target": "L423-1"},
    ],
}


class TestGraphFromImport:
    def test_referenced_by_is_recomputed_from_edges(self):
        graph = graph_from_import(GRAPHE)
        assert sorted(graph.nodes["L423-1"]["referenced_by"]) == ["Annexe 10", "L423-3"]
        assert graph.nodes["L423-3"]["referenced_by"] == []

    def test_defaults_and_self_loops(self):
        graph = graph_from_import(GRAPHE)
        assert graph.nodes["Annexe 10"]["label"] == "Annexe 10"
        assert graph.number_of_edges() == 2
        assert graph.edges["L423-3", "L423-1"]["description"] == "cite"
        assert graph.edges["L423-3", "L423-1"]["origine"] == "legi"

    @pytest.mark.parametrize("data, fragment", [
        ({"nodes": [], "edges": []}, "non vide"),
        ({"nodes": [{"label": "sans id"}], "edges": []}, "« id »"),
        ({"nodes": [{"id": "A"}, {"id": "A"}], "edges": []}, "en double"),
        ({"nodes": [{"id": "A"}], "edges": [{"source": "A", "target": "B"}]}, "nœud absent"),
    ])
    def test_malformed_graphs_are_refused(self, data, fragment):
        with pytest.raises(GraphImportError, match=fragment):
            graph_from_import(data)

    def test_origin_survives_a_disk_round_trip(self, tmp_path):
        GraphBuilder(data_dir=str(tmp_path)).import_graph("ceseda", GRAPHE, imported_by="g1")
        reloaded = GraphBuilder(data_dir=str(tmp_path))
        assert reloaded.is_imported("ceseda")
        assert reloaded.get("ceseda").graph["imported_by"] == "g1"
        assert json.loads((tmp_path / "ceseda" / "graph.json").read_text())["meta"]["origin"] == "import"


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    import app.config
    import app.routers.graph as graph_router
    monkeypatch.setattr(app.config.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(graph_router, "_builder", GraphBuilder(data_dir=str(tmp_path)))
    from app.main import app
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield app, client
    app.dependency_overrides.clear()


def _as(app, user: CurrentUser):
    app.dependency_overrides[current_user] = lambda: user


def _create(app, client, name: str):
    _as(app, SUPERADMIN)
    with patch("app.routers.collections.OpenRAGClient") as mock_cls:
        mock_cls.return_value.create_partition = AsyncMock(return_value={})
        r = client.post("/api/collections", json={"name": name, "scope": "public"})
    assert r.status_code in (200, 409), r.text


class TestImportEndpoint:
    def test_manager_imports_and_viewer_reads_it(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        r = client.put("/graph/grimp-ceseda", json=GRAPHE)
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "imported", "collection": "grimp-ceseda", "nodes": 3, "edges": 2}
        data = client.get("/graph/data", params={"corpus_id": "grimp-ceseda"}).json()
        assert data["graph_ready"] is True and data["total_nodes"] == 3

    def test_import_turns_the_graph_on_for_the_collection(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        client.put("/graph/grimp-ceseda", json=GRAPHE)
        assert client.get("/api/collections/grimp-ceseda").json()["graph_enabled"] is True

    def test_non_manager_is_refused(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, LECTEUR)
        assert client.put("/graph/grimp-ceseda", json=GRAPHE).status_code == 403

    def test_unknown_collection_is_404(self, app_client):
        app, client = app_client
        _as(app, SUPERADMIN)
        assert client.put("/graph/grimp-inconnue", json=GRAPHE).status_code == 404

    def test_malformed_graph_is_422_with_a_reason(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        r = client.put("/graph/grimp-ceseda", json={"nodes": [{"id": "A"}], "edges": [{"source": "A", "target": "B"}]})
        assert r.status_code == 422 and "nœud absent" in r.json()["detail"]

    def test_build_refuses_to_overwrite_an_imported_graph(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        client.put("/graph/grimp-ceseda", json=GRAPHE)
        r = client.post("/graph/grimp-ceseda/build")
        assert r.status_code == 409 and "force=true" in r.json()["detail"]


class TestBuildAndSummarizeAreReservedToManagers:
    """Ces deux routes réécrivent le graphe sur disque : elles étaient ouvertes à tous."""

    def test_non_manager_cannot_rebuild(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, LECTEUR)
        with patch("app.services.openrag_client.OpenRAGClient") as mock_cls:
            r = client.post("/graph/grimp-ceseda/build")
        assert r.status_code == 403
        mock_cls.assert_not_called()

    def test_non_manager_cannot_force_over_an_imported_graph(self, app_client, tmp_path):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        client.put("/graph/grimp-ceseda", json=GRAPHE)
        avant = (tmp_path / "grimp-ceseda" / "graph.json").read_text()
        _as(app, LECTEUR)
        assert client.post("/graph/grimp-ceseda/build", params={"force": "true"}).status_code == 403
        assert (tmp_path / "grimp-ceseda" / "graph.json").read_text() == avant

    def test_manager_can_force_a_rebuild(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        client.put("/graph/grimp-ceseda", json=GRAPHE)
        documents = [{"content": "Voir l'article L. 423-1.", "metadata": {"filename": "Article-L423-3.md"}},
                     {"content": "Conjoint de Français.", "metadata": {"filename": "Article-L423-1.md"}}]
        with patch("app.services.openrag_client.OpenRAGClient") as mock_cls:
            mock_cls.return_value.search = AsyncMock(return_value={"documents": documents})
            r = client.post("/graph/grimp-ceseda/build", params={"force": "true"})
        assert r.status_code == 200, r.text
        assert r.json()["nodes"] == 2

    def test_superadmin_can_rebuild_a_partition_without_a_fiche(self, app_client):
        app, client = app_client
        _as(app, SUPERADMIN)
        with patch("app.services.openrag_client.OpenRAGClient") as mock_cls:
            mock_cls.return_value.search = AsyncMock(return_value={"documents": []})
            r = client.post("/graph/grimp-sans-fiche/build")
        assert r.status_code == 404 and "No documents" in r.json()["detail"]

    def test_non_manager_cannot_summarize(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, LECTEUR)
        r = client.post("/graph/grimp-ceseda/summarize", params={"llm_url": "http://exemple.invalid"})
        assert r.status_code == 403

    def test_manager_reaches_summarize(self, app_client):
        app, client = app_client
        _create(app, client, "grimp-ceseda")
        _as(app, GESTIONNAIRE)
        r = client.post("/graph/grimp-ceseda/summarize")
        assert r.status_code == 200 and r.json()["status"] == "disabled"

