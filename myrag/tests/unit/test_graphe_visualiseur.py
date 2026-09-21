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


# ─── « Partie du corpus » : le sélecteur qui ne servait à rien ──────────────────────────────

def _code():
    g = nx.DiGraph()
    for article, livre in (("L. 110-1", "I"), ("L. 421-1", "IV"), ("L. 421-2", "IV"), ("L. 511-1", "V"), ("L. 900-1", "IX"), ("Annexe 1", "")):
        g.add_node(article, label=f"Article {article}", livre=livre, content_preview="")
    g.add_edge("L. 421-1", "L. 421-2")
    g.add_edge("L. 421-1", "L. 511-1")
    return g


def _reponse(monkeypatch, graphe, **params):
    b = GraphBuilder()
    monkeypatch.setattr(b, "get", lambda collection: graphe)
    return b.to_graph_data_response(collection="c", **{"query": "", "max_nodes": 80, "min_weight": 0.0, **params})


def test_le_selecteur_recoit_des_options_lisibles_en_ordre_romain(monkeypatch):
    sources = _reponse(monkeypatch, _code())["available_sources"]
    assert sources[0] == {"id": "", "label": "Tout le corpus"}
    assert [s["label"] for s in sources[1:]] == ["Livre I", "Livre IV", "Livre V", "Livre IX", "Hors livres"]   # IX APRÈS V
    assert all(set(s) == {"id", "label"} and isinstance(s["label"], str) and s["label"] for s in sources)


def test_choisir_un_livre_restreint_vraiment_le_graphe(monkeypatch):
    tout = _reponse(monkeypatch, _code())
    livre4 = _reponse(monkeypatch, _code(), source_prefix="Livre-IV")
    assert tout["total_nodes"] == 6 and tout["source_prefix"] == ""
    assert {n["id"] for n in livre4["nodes"]} == {"L. 421-1", "L. 421-2"} and livre4["source_prefix"] == "Livre-IV"
    assert livre4["total_edges"] == 1   # le lien vers le Livre V sort avec lui
    assert len(livre4["available_sources"]) == len(tout["available_sources"])   # la liste ne dépend pas du filtre
    hors = _reponse(monkeypatch, _code(), source_prefix="other")
    assert {n["id"] for n in hors["nodes"]} == {"Annexe 1"}


def test_une_partie_inconnue_est_ignoree_et_dite(monkeypatch):
    r = _reponse(monkeypatch, _code(), source_prefix="Livre-XLII")
    assert r["total_nodes"] == 6 and r["source_prefix"] == ""


def test_partie_et_filtre_se_combinent(monkeypatch):
    r = _reponse(monkeypatch, _code(), source_prefix="Livre-IV", query="421-2")
    assert r["query_matched"] is True and {n["id"] for n in r["nodes"]} <= {"L. 421-1", "L. 421-2"}
    ailleurs = _reponse(monkeypatch, _code(), source_prefix="Livre-IV", query="511-1")   # existe, mais dans le Livre V
    assert ailleurs["query_matched"] is False


def test_un_corpus_sans_parties_n_offre_pas_de_faux_choix(monkeypatch):
    g = nx.DiGraph(); g.add_node("a", label="A"); g.add_node("b", label="B")
    assert _reponse(monkeypatch, g)["available_sources"] == [{"id": "", "label": "Tout le corpus"}]


def test_sans_graphe_le_visualiseur_recoit_quand_meme_sa_liste(monkeypatch):
    b = GraphBuilder()
    monkeypatch.setattr(b, "get", lambda collection: None)
    r = b.to_graph_data_response(collection="c", query="", max_nodes=80, min_weight=0.0)
    assert r["graph_ready"] is False and r["available_sources"] == [{"id": "", "label": "Tout le corpus"}]


def test_la_route_transmet_la_partie(client, monkeypatch):
    from app.routers import graph as routes
    monkeypatch.setattr(routes._builder, "get", lambda collection: _code())
    r = client.get("/graph/data", params={"corpus_id": "c", "source_prefix": "Livre-V"}).json()
    assert [n["id"] for n in r["nodes"]] == ["L. 511-1"] and r["source_prefix"] == "Livre-V"
