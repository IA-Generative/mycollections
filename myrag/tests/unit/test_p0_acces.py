"""Diagnostic d'octobre 2026, P0 : ce qui répondait sans jeton ni droit.

- les avis (questions et réponses des utilisateurs) : lus et traités par qui GÈRE la collection,
  donnés par qui la LIT ;
- la synchronisation avec le SSO : superadmin seul ;
- le diagnostic de l'assistant : superadmin seul ;
- la description de l'API (/docs, /openapi.json, /redoc) : pas servie hors développement.
"""

from unittest.mock import AsyncMock, patch

from app.auth import CurrentUser
from tests.conftest import SUPERADMIN, personne

ETRANGER = CurrentUser(sub="etranger", username="e", groups=["/g/rien-a-voir"])


def _avis(client, nom):
    return client.post("/api/feedback/ingest", json={
        "collection": nom, "question": "Q ?", "response": "R.", "rating": -1})


def test_qui_lit_la_collection_peut_donner_un_avis(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    assert _avis(client, nom).status_code == 200


def test_qui_ne_lit_pas_la_collection_ne_donne_pas_d_avis(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(ETRANGER)
    assert _avis(client, nom).status_code == 404


def test_les_avis_ne_se_lisent_que_par_qui_gere(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    fb = _avis(client, nom).json()["id"]
    assert client.get(f"/api/feedback/{nom}").status_code == 403
    assert client.patch(f"/api/feedback/{nom}/{fb}/review", json={"status": "reviewed"}).status_code == 403
    assert client.post(f"/api/feedback/{nom}/{fb}/promote", json={"promote_to": "qr"}).status_code == 403
    en_tant_que(ETRANGER)
    assert client.get(f"/api/feedback/{nom}").status_code == 404
    assert client.get(f"/api/feedback/{nom}/stats").status_code == 404
    en_tant_que(personne("createur"))
    liste = client.get(f"/api/feedback/{nom}")
    assert liste.status_code == 200 and [f["id"] for f in liste.json()["feedback"]] == [fb]
    assert client.patch(f"/api/feedback/{nom}/{fb}/review", json={"status": "reviewed"}).status_code == 200


def test_un_avis_ne_se_traite_que_dans_sa_collection(client, en_tant_que, creer_collection, nom):
    """Gérer la collection A ne donne pas la main sur un avis de la collection B."""
    autre = nom[:-2] + "zz"
    creer_collection(nom)
    creer_collection(autre, createur=personne("autre-createur"))
    en_tant_que(personne("lecteur"))
    fb_autre = _avis(client, autre).json()["id"]
    en_tant_que(personne("createur"))
    assert client.patch(f"/api/feedback/{nom}/{fb_autre}/review", json={"status": "reviewed"}).status_code == 404
    assert client.post(f"/api/feedback/{nom}/{fb_autre}/promote", json={"promote_to": "qr"}).status_code == 404


def test_la_synchronisation_du_sso_est_reservee_a_l_administration(client, en_tant_que):
    en_tant_que(personne("quelqu-un"))
    assert client.get("/api/sync/groups").status_code == 403
    assert client.post("/api/sync/create-group", json={"name": "x"}).status_code == 403
    assert client.post("/api/sync").status_code == 403
    assert client.post("/api/sync/une-collection").status_code == 403
    en_tant_que(SUPERADMIN)
    with patch("app.services.keycloak_client.KeycloakClient._ensure_root_group", new=AsyncMock(side_effect=RuntimeError)):
        assert client.get("/api/sync/groups").status_code == 200


def test_le_diagnostic_de_l_assistant_est_reserve_a_l_administration(client, en_tant_que):
    en_tant_que(personne("quelqu-un"))
    assert client.get("/api/owui/probe").status_code == 403


def test_la_description_de_l_api_n_est_pas_publique(client):
    for chemin in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(chemin).status_code == 404, chemin


def test_la_fiche_dit_a_l_appelant_ce_qu_il_peut_faire(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    d = client.get(f"/api/collections/{nom}").json()["mes_droits"]
    assert d == {"lire": True, "ecrire": True, "garant": True, "superadmin": False}, "le créateur en est le garant"
    en_tant_que(personne("lecteur"))
    d = client.get(f"/api/collections/{nom}").json()["mes_droits"]
    assert d["ecrire"] is False and d["garant"] is False
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.list_models = AsyncMock(return_value={"data": []})
        cls.return_value.list_files = AsyncMock(return_value=[])
        liste = client.get("/api/collections").json()["collections"]
    assert next(c for c in liste if c["name"] == nom)["mes_droits"]["ecrire"] is False


def test_moi_dit_si_l_appelant_administre(client, en_tant_que):
    en_tant_que(personne("quelqu-un"))
    assert client.get("/api/moi").json() == {"superadmin": False}
    en_tant_que(SUPERADMIN)
    assert client.get("/api/moi").json() == {"superadmin": True}
