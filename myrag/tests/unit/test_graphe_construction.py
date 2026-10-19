"""Diagnostic d'octobre 2026, P2 : « construire le graphe » répondait 404 « No documents »
même après une indexation réussie. Il cherchait les morceaux par une recherche sémantique
« * », que le seuil de pertinence d'OpenRAG vide. Écrit avant le correctif, relu pour
l'ADR-0005 : la construction découpe les sources conservées sur le disque (par article),
sans interroger OpenRAG ; sans aucun article, elle refuse sans écraser le graphe existant."""

from unittest.mock import AsyncMock, patch

from app.services.openrag_client import ReponseChat
from tests.unit.test_graph_import import (  # noqa: F401
    CESEDA,
    SUPERADMIN,
    _as,
    _create,
    _deposer,
    app_client,  # noqa: F401  (fixture)
)


def test_la_construction_lit_les_sources_conservees(app_client):
    app, client = app_client
    _create(app, client, "gcons-ceseda")
    _as(app, SUPERADMIN)
    _deposer(client, "gcons-ceseda", "ceseda.md", CESEDA)
    r = client.post("/graph/gcons-ceseda/build")
    assert r.status_code == 200, r.text
    assert r.json()["nodes"] == 2 and r.json()["edges"] == 1


def test_sans_article_elle_refuse_sans_ecraser_le_graphe(app_client):
    app, client = app_client
    _create(app, client, "gcons-vide")
    _as(app, SUPERADMIN)
    _deposer(client, "gcons-vide", "ceseda.md", CESEDA)
    assert client.post("/graph/gcons-vide/build").status_code == 200
    # La source est remplacée par un texte sans article : reconstruire refuse, et le
    # graphe déjà construit reste en place.
    from app.routers.ingest import SOURCES_DIR

    (SOURCES_DIR / "gcons-vide" / "ceseda.md").write_text("Préambule.")
    r = client.post("/graph/gcons-vide/build", params={"force": "true"})
    assert r.status_code == 422 and "article" in r.json()["detail"].lower()
    assert client.get("/graph/data", params={"corpus_id": "gcons-vide"}).json()["total_nodes"] == 2


def test_le_resume_ia_relit_les_sources_sans_adresse_fournie_par_l_appelant(app_client):
    """Avant : 500 garanti (attribut lu sur un dict), sources cherchées au mauvais endroit, et
    le serveur appelait l'adresse de modèle fournie par l'appelant (rebond réseau)."""
    app, client = app_client
    _create(app, client, "gcons-resume")
    _as(app, SUPERADMIN)
    _deposer(client, "gcons-resume", "long.md", "Article L1\n\n" + "très long. " * 120)
    assert client.post("/graph/gcons-resume/build").status_code == 200
    with patch("app.services.openrag_client.OpenRAGClient") as cls:
        c = cls.return_value
        c.chat = AsyncMock(return_value=ReponseChat.model_validate({"choices": [{"message": {"content": "Cet article dit l'essentiel."}}]}))
        r = client.post("/graph/gcons-resume/summarize", params={"threshold": 100, "llm_url": "http://169.254.169.254/"})
    assert r.status_code == 200, r.text
    assert r.json()["summarized"] == 1
    appel = c.chat.await_args
    assert appel is not None
    assert appel.kwargs.get("model") == "openrag-gcons-resume"
