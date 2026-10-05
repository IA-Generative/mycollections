"""Diagnostic d'octobre 2026, P2 : « construire le graphe » répondait 404 « No documents »
même après une indexation réussie. Il cherchait les morceaux par une recherche sémantique
« * », que le seuil de pertinence d'OpenRAG vide. Écrit avant le correctif : la construction
liste les fichiers de la partition et lit leur contenu ; sans aucun article, elle refuse
sans écraser le graphe existant."""

from unittest.mock import AsyncMock, patch

from tests.unit.test_graph_import import SUPERADMIN, _as, _create  # noqa: F401
from tests.unit.test_graph_import import app_client  # noqa: F401  (fixture)

FICHIERS = [{"file_id": "11", "filename": "Article-L423-3.md"},
            {"file_id": "12", "original_filename": "Article-L423-1.md"},
            {"file_id": "13", "filename": "section-preambule.md"}]
CONTENUS = {"11": "Voir l'article L. 423-1.", "12": "Conjoint de Français.", "13": "Préambule."}


def _openrag(mock_cls, fichiers=FICHIERS):
    client = mock_cls.return_value
    client.search = AsyncMock(return_value={"documents": []})  # ce que rend « * » en vrai
    client.list_files = AsyncMock(return_value=fichiers)
    client.get_file_content = AsyncMock(side_effect=lambda p, f: CONTENUS.get(f, ""))
    return client


def test_la_construction_lit_les_fichiers_de_la_partition(app_client):
    app, client = app_client
    _create(app, client, "gcons-ceseda")
    _as(app, SUPERADMIN)
    with patch("app.services.openrag_client.OpenRAGClient") as cls:
        _openrag(cls)
        r = client.post("/graph/gcons-ceseda/build")
    assert r.status_code == 200, r.text
    assert r.json()["nodes"] == 2 and r.json()["edges"] == 1


def test_sans_article_elle_refuse_sans_ecraser_le_graphe(app_client, tmp_path):
    app, client = app_client
    _create(app, client, "gcons-vide")
    _as(app, SUPERADMIN)
    with patch("app.services.openrag_client.OpenRAGClient") as cls:
        _openrag(cls)
        assert client.post("/graph/gcons-vide/build").status_code == 200
        _openrag(cls, fichiers=[{"file_id": "13", "filename": "section-preambule.md"}])
        r = client.post("/graph/gcons-vide/build", params={"force": "true"})
    assert r.status_code == 422 and "article" in r.json()["detail"].lower()
    assert client.get("/graph/data", params={"corpus_id": "gcons-vide"}).json()["total_nodes"] == 2


def test_le_resume_ia_fonctionne_par_openrag_sans_adresse_fournie_par_l_appelant(app_client, tmp_path):
    """Avant : 500 garanti (attribut lu sur un dict), sources cherchées au mauvais endroit, et
    le serveur appelait l'adresse de modèle fournie par l'appelant (rebond réseau)."""
    app, client = app_client
    _create(app, client, "gcons-resume")
    _as(app, SUPERADMIN)
    long_texte = "Article L1 très long. " * 120
    fichiers = [{"file_id": "1", "filename": "Article-L1.md"}]
    with patch("app.services.openrag_client.OpenRAGClient") as cls:
        c = cls.return_value
        c.list_files = AsyncMock(return_value=fichiers)
        c.get_file_content = AsyncMock(return_value=long_texte)
        c.chat = AsyncMock(return_value={"choices": [{"message": {"content": "Cet article dit l'essentiel."}}]})
        assert client.post("/graph/gcons-resume/build").status_code == 200
        r = client.post("/graph/gcons-resume/summarize", params={"threshold": 100, "llm_url": "http://169.254.169.254/"})
    assert r.status_code == 200, r.text
    assert r.json()["summarized"] == 1
    assert c.chat.await_args.kwargs.get("model") == "openrag-gcons-resume" or c.chat.await_args.args[0] == "openrag-gcons-resume"
