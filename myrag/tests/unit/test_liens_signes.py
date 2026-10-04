"""Diagnostic d'octobre 2026, P0 : ce qu'un navigateur ouvre sans jeton (sources, graphe,
articles) n'est plus ouvert à tous. On entre par une collection publiée à tous, un lien signé
remis par le serveur, ou un jeton qui lit la collection.

Ces tests activent l'authentification (la suite tourne sans) et remplacent la vérification
du jeton par l'identité voulue.
"""

import time

import httpx
import pytest

from app.auth import CurrentUser
from app.services import liens
from tests.conftest import personne

ETRANGER = CurrentUser(sub="etranger", username="e", groups=["/g/rien-a-voir"])


@pytest.fixture
def auth(monkeypatch):
    """`auth(u)` met l'authentification en service (après la création des collections, qui se
    fait sans) et fait comme si la requête portait le jeton de `u` (None : aucun jeton)."""
    from app.config import settings
    from app.routers import _acces_navigateur as garde
    qui = {"u": None}

    async def _facultatif(credentials):
        return qui["u"]

    def activer(u=None):
        monkeypatch.setattr(settings, "auth_enabled", True)
        monkeypatch.setattr(garde, "utilisateur_facultatif", _facultatif)
        qui["u"] = u
    return activer


@pytest.fixture
def faux_openrag(monkeypatch):
    class _R:
        def __init__(self, status, content, headers):
            self.status_code, self.content, self.headers = status, content, headers

    class FauxClient:
        partition = "x"
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            corps = ('{"page_content": "texte", "metadata": {"partition": "%s"}}' % FauxClient.partition).encode()
            return _R(200, corps, {"content-type": "application/json"})
    monkeypatch.setattr(httpx, "AsyncClient", FauxClient)
    return FauxClient


def test_sans_jeton_ni_signature_une_collection_non_publique_est_fermee(client, creer_collection, nom, auth):
    creer_collection(nom)
    auth()
    assert client.get(f"/graph/data?corpus_id={nom}").status_code == 401
    assert client.get(f"/graph/{nom}/related?article=L1").status_code == 401
    assert client.get(f"/articles/{nom}/L1").status_code == 401
    assert client.get("/api/openrag/extract/12").status_code == 401
    assert client.get("/api/openrag/static/12").status_code == 401
    assert client.get("/api/openrag/file/12").status_code == 401


def test_un_lien_signe_ouvre_la_vue_de_sa_collection_seulement(client, creer_collection, nom, auth):
    creer_collection(nom)
    auth()
    q = liens.parametres(liens.portee_graphe(nom))
    assert client.get(f"/graph/data?corpus_id={nom}&exp={q['exp']}&sig={q['sig']}").status_code == 200
    assert client.get(f"/articles/{nom}/L1?exp={q['exp']}&sig={q['sig']}").status_code == 404  # passé la garde : pas de graphe
    autre = liens.parametres(liens.portee_graphe("une-autre"))
    assert client.get(f"/graph/data?corpus_id={nom}&exp={autre['exp']}&sig={autre['sig']}").status_code == 401


def test_un_lien_expire_ne_vaut_plus(client, creer_collection, nom, auth):
    creer_collection(nom)
    auth()
    q = liens.parametres(liens.portee_graphe(nom), duree_s=-1)
    assert client.get(f"/graph/data?corpus_id={nom}&exp={q['exp']}&sig={q['sig']}").status_code == 401
    assert not liens.valide(liens.portee_graphe(nom), str(int(time.time()) + 60), "0" * 40)


def test_un_extrait_signe_s_ouvre_sans_jeton(client, auth, faux_openrag):
    auth()
    q = liens.parametres(liens.portee_extrait("12"))
    assert client.get(f"/api/openrag/extract/12?exp={q['exp']}&sig={q['sig']}").status_code == 200
    assert client.get(f"/api/openrag/extract/13?exp={q['exp']}&sig={q['sig']}").status_code == 401


def test_avec_un_jeton_on_lit_ce_qu_on_peut_lire(client, creer_collection, nom, auth, faux_openrag):
    creer_collection(nom)
    auth()
    faux_openrag.partition = nom
    auth(personne("lecteur"))
    assert client.get(f"/graph/data?corpus_id={nom}").status_code == 200
    assert client.get("/api/openrag/extract/12").status_code == 200
    auth(ETRANGER)
    assert client.get(f"/graph/data?corpus_id={nom}").status_code == 404
    assert client.get("/api/openrag/extract/12").status_code == 404, "le morceau appartient à une collection qu'il ne lit pas"


def test_une_collection_publiee_a_tous_reste_ouverte_a_l_outil_de_l_assistant(client, creer_collection, nom, auth):
    import sqlite3, os
    creer_collection(nom)
    auth()
    chemin = os.environ["DATABASE_URL"].split("///")[-1]
    con = sqlite3.connect(chemin)
    try:
        con.execute("INSERT OR REPLACE INTO publications (collection_name, state, alias_enabled, alias_name, "
                    "alias_description, tool_enabled, embed_enabled, visibility, visibility_groups_json, "
                    "widget_enabled, browser_enabled, published_by) "
                    "VALUES (?, 'published', 1, '', '', 0, 0, 'all', '[]', 0, 0, '')", (nom,))
        con.commit()
    finally:
        con.close()
    assert client.get(f"/graph/data?corpus_id={nom}").status_code == 200


def test_la_fiche_obtient_l_adresse_signee_du_visualiseur(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    r = client.get(f"/graph/{nom}/lien")
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith(f"/graph?corpus_id={nom}&exp=") and "&sig=" in url
    en_tant_que(ETRANGER)
    assert client.get(f"/graph/{nom}/lien").status_code == 404


def test_un_morceau_du_repli_recoit_un_lien_signe_depuis_son_identifiant():
    from app.routers.playground import signer_les_liens_de_la_source
    s = signer_les_liens_de_la_source({"_id": 468450154026104240, "content": "x"})
    assert s["chunk_url"].startswith("/api/openrag/extract/468450154026104240?exp=")
    exp, sig = s["chunk_url"].split("exp=")[1].split("&sig=")
    assert liens.valide(liens.portee_extrait("468450154026104240"), exp, sig)
    assert "chunk_url" not in signer_les_liens_de_la_source({"_id": "pas-un-nombre"})
