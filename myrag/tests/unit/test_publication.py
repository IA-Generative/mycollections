"""Cycle de publication : brouillon → publiée → désactivée → archivée, et son historique.

Réécrit le 2026-10-04 sur la base (l'ancienne version lisait un `metadata.json` disque et
simulait un `OpenRAGClient` que le routeur n'importe plus). Les droits sont couverts par
`test_publication_droits.py` ; ici, le gestionnaire fait chaque geste et on lit l'état.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.collection import PublicationConfig
from tests.conftest import personne

PUBLIER = {"alias_enabled": True, "visibility": "group", "visibility_groups": ["/g/mirai-beta-testeurs"]}


@pytest.fixture
def socle():
    with patch("app.services.fiche_assistant.synchroniser_fiche", new=AsyncMock(return_value={"nom": "x"})) as m, \
         patch("app.services.owui_client.OwuiClient.delete_model", new=AsyncMock(return_value=None)):
        yield m


def test_l_etat_par_defaut_est_brouillon():
    assert PublicationConfig().state == "draft"


def test_une_collection_neuve_est_en_brouillon(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    r = client.get(f"/api/collections/{nom}/publication")
    assert r.status_code == 200 and r.json()["state"] in ("draft", None)


def test_publier_desactiver_archiver(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    r = client.post(f"/api/collections/{nom}/publish", json=PUBLIER)
    assert r.status_code == 200, r.text
    assert client.get(f"/api/collections/{nom}/publication").json()["state"] == "published"

    assert client.post(f"/api/collections/{nom}/unpublish").status_code == 200
    assert client.get(f"/api/collections/{nom}/publication").json()["state"] == "disabled"

    assert client.post(f"/api/collections/{nom}/archive").status_code == 200
    assert client.get(f"/api/collections/{nom}").json().get("archived_at")


def test_l_historique_garde_les_gestes(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    client.post(f"/api/collections/{nom}/publish", json=PUBLIER)
    client.post(f"/api/collections/{nom}/unpublish")
    r = client.get(f"/api/collections/{nom}/publication/history")
    assert r.status_code == 200
    assert len(r.json()["history"]) >= 2


def test_publier_une_collection_inconnue_rend_404_a_qui_ne_peut_pas_la_gerer(client, en_tant_que, socle):
    """Un superadmin peut adopter une partition sans fiche ; une personne ordinaire, non."""
    en_tant_que(personne("quelqu-un"))
    assert client.post("/api/collections/inconnue-de-tous/publish", json=PUBLIER).status_code == 404
    socle.assert_not_awaited()
