"""Le visualiseur de graphe : ce qu'il sait de l'assistant, et un filtre qui dit quand il ne trouve rien."""

import networkx as nx

from app.config import settings
from app.routers.graph import injecter_config
from app.services.graph_builder import GraphBuilder
from tests.conftest import personne


def _publier(client, en_tant_que, nom, *, visibilite, createur):
    from unittest.mock import AsyncMock, patch
    en_tant_que(createur)
    with patch("app.services.fiche_assistant.synchroniser_fiche", new=AsyncMock(return_value={"nom": "x"})):
        r = client.post(f"/api/collections/{nom}/publish",
                        json={"alias_enabled": True, "visibility": visibilite, "visibility_groups": ["/g/mirai-beta-testeurs"]})
    assert r.status_code == 200, r.text


def _config(client, nom):
    import json
    import re
    page = client.get("/graph", params={"corpus_id": nom}).text
    return json.loads(re.search(r"window\.GRAPH_VIEWER_CONFIG = (\{.*?\});</script>", page).group(1))


def test_sans_adresse_publique_de_l_assistant_rien_n_est_offert(client, monkeypatch, nom):
    monkeypatch.setattr(settings, "owui_public_url", "")
    assert _config(client, nom) == {"openwebui_url": "", "assistant_model": ""}


def test_le_modele_n_est_dit_que_pour_une_collection_publiee_a_tous(client, en_tant_que, creer_collection, nom, monkeypatch):
    monkeypatch.setattr(settings, "owui_public_url", "https://assistant.exemple/")
    createur = personne("createur-graphe")
    creer_collection(nom, createur)
    assert _config(client, nom) == {"openwebui_url": "https://assistant.exemple", "assistant_model": ""}   # pas publiée

    _publier(client, en_tant_que, nom, visibilite="group", createur=createur)
    assert _config(client, nom)["assistant_model"] == ""   # publiée à un groupe : cette page, servie sans session, n'en dit rien


def test_publiee_a_tous_le_visualiseur_connait_son_modele(client, en_tant_que, creer_collection, nom, monkeypatch):
    monkeypatch.setattr(settings, "owui_public_url", "https://assistant.exemple")
    createur = personne("createur-graphe")
    creer_collection(nom, createur, etat_collab="publiee_tous")
    import sqlite3, os
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.execute("UPDATE collections SET etat_collab='publiee_tous' WHERE name=?", (nom,)); con.commit(); con.close()
    _publier(client, en_tant_que, nom, visibilite="all", createur=createur)
    assert _config(client, nom) == {"openwebui_url": "https://assistant.exemple", "assistant_model": f"openrag-{nom}"}

    en_tant_que(createur)
    client.post(f"/api/collections/{nom}/archive")
    assert _config(client, nom)["assistant_model"] == ""   # archivée : plus offerte


def test_une_valeur_ne_peut_pas_refermer_la_balise_script():
    page = injecter_config("<html><body><p>x</p></body></html>", {"openwebui_url": "</script><script>alert(1)</script>"})
    assert page.count("<script>") == 1 and page.count("</script>") == 1   # la nôtre, et elle seule
    assert "alert(1)" in page and "\\u003c/script>" in page               # la valeur est là, inerte


def test_le_filtre_dit_quand_il_ne_trouve_rien(monkeypatch):
    g = nx.DiGraph()
    g.add_node("L. 421-1", label="Article L. 421-1", content_preview="carte de séjour temporaire")
    g.add_node("L. 421-2", label="Article L. 421-2", content_preview="renouvellement")
    g.add_edge("L. 421-1", "L. 421-2")
    b = GraphBuilder()
    monkeypatch.setattr(b, "get", lambda collection: g)
    trouve = b.to_graph_data_response(collection="c", query="421-1", max_nodes=80, min_weight=0.0)
    rien = b.to_graph_data_response(collection="c", query="Compare le traité de Brétigny et le traité de Troyes", max_nodes=80, min_weight=0.0)
    sans = b.to_graph_data_response(collection="c", query="", max_nodes=80, min_weight=0.0)
    assert (trouve["query_matched"], rien["query_matched"], sans["query_matched"]) == (True, False, True)
    assert rien["total_nodes"] == 2   # le graphe entier est rendu — et désormais on le sait
