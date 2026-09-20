"""Publier, dépublier, archiver, désarchiver sont des gestes d'ÉCRITURE.

Avant ce correctif, ces quatre routes ne demandaient qu'« être connecté » : tout compte
pouvait archiver la collection d'un autre. Et publier une collection archivée passait
l'état local à « publiée » pour échouer ensuite sur un message qui ne disait que son nom —
c'est ce qui est arrivé à `ceseda-legifrance` le 2026-09-20, après un clic sur « Archiver ».
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.auth import CurrentUser
from app.routers.publication import MESSAGE_ARCHIVEE
from tests.conftest import SUPERADMIN, personne

ETRANGER = CurrentUser(sub="etranger", username="e", groups=["/g/rien-a-voir"])
GESTES = ("archive", "unarchive", "unpublish")
PUBLIER = {"alias_enabled": True, "visibility": "group", "visibility_groups": ["/g/mirai-beta-testeurs"]}


def _archivee(client, nom) -> bool:
    return bool(client.get(f"/api/collections/{nom}").json().get("archived_at"))


@pytest.fixture
def socle():
    """La synchronisation vers l'assistant, remplacée : ces tests ne parlent pas à OpenWebUI."""
    with patch("app.services.fiche_assistant.synchroniser_fiche", new=AsyncMock(return_value={"nom": "x"})) as m:
        yield m


def test_qui_ne_lit_pas_la_collection_ne_peut_rien_et_n_apprend_rien(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom, scope="group", scope_groups=["/g/un-autre-groupe"])
    en_tant_que(ETRANGER)
    for geste in GESTES:
        assert client.post(f"/api/collections/{nom}/{geste}").status_code == 404, geste
    assert client.post(f"/api/collections/{nom}/publish", json=PUBLIER).status_code == 404
    assert client.get(f"/api/collections/{nom}/publication").status_code == 404
    assert client.get(f"/api/collections/{nom}/publication/history").status_code == 404
    socle.assert_not_awaited()
    en_tant_que(SUPERADMIN)
    assert not _archivee(client, nom)  # le geste refusé n'a rien fait


def test_qui_lit_sans_gerer_voit_l_etat_mais_ne_peut_pas_ecrire(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom)  # lisible du groupe des testeurs, créée par « createur »
    en_tant_que(personne("simple-lecteur"))
    assert client.get(f"/api/collections/{nom}/publication").status_code == 200
    assert client.get(f"/api/collections/{nom}/publication/history").status_code == 200
    for geste in GESTES:
        assert client.post(f"/api/collections/{nom}/{geste}").status_code == 403, geste
    assert client.post(f"/api/collections/{nom}/publish", json=PUBLIER).status_code == 403
    socle.assert_not_awaited()
    en_tant_que(SUPERADMIN)
    assert not _archivee(client, nom)


def test_une_collection_inconnue_rend_404_a_tout_le_monde_sauf_a_qui_pourrait_la_gerer(client, en_tant_que):
    en_tant_que(personne("quelqu-un"))
    assert client.post("/api/collections/partition-sans-fiche-xyz/archive").status_code == 404
    assert client.get("/api/collections/partition-sans-fiche-xyz/publication").status_code == 404


def test_le_createur_archive_et_une_collection_archivee_refuse_d_etre_publiee(client, en_tant_que, creer_collection, nom, socle):
    createur = personne("createur")
    creer_collection(nom, createur)
    en_tant_que(createur)
    assert client.post(f"/api/collections/{nom}/archive").status_code == 200
    assert client.get(f"/api/collections/{nom}/publication").json()["archivee"] is True

    r = client.post(f"/api/collections/{nom}/publish", json=PUBLIER)
    assert r.status_code == 409 and r.json()["detail"] == MESSAGE_ARCHIVEE
    socle.assert_not_awaited()
    assert client.get(f"/api/collections/{nom}/publication").json()["state"] != "published"  # l'état local n'a pas menti

    assert client.post(f"/api/collections/{nom}/unarchive").status_code == 200
    assert client.get(f"/api/collections/{nom}/publication").json()["archivee"] is False
    r = client.post(f"/api/collections/{nom}/publish", json=PUBLIER)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "published" and r.json()["owui"]["synced"] is True
    socle.assert_awaited_once()


def test_un_brouillon_s_enregistre_meme_archivee(client, en_tant_que, creer_collection, nom, socle):
    createur = personne("createur")
    creer_collection(nom, createur)
    en_tant_que(createur)
    client.post(f"/api/collections/{nom}/archive")
    assert client.post(f"/api/collections/{nom}/publish", json={**PUBLIER, "state": "draft"}).status_code == 200
    socle.assert_not_awaited()


def test_le_superadmin_gere_toutes_les_collections(client, en_tant_que, creer_collection, nom, socle):
    creer_collection(nom)
    en_tant_que(SUPERADMIN)
    assert client.post(f"/api/collections/{nom}/archive").status_code == 200
    assert client.post(f"/api/collections/{nom}/unarchive").status_code == 200


def test_un_echec_de_l_assistant_se_dit_en_clair(client, en_tant_que, creer_collection, nom):
    createur = personne("createur")
    creer_collection(nom, createur)
    en_tant_que(createur)
    with patch("app.services.fiche_assistant.synchroniser_fiche", new=AsyncMock(side_effect=RuntimeError("socle injoignable"))):
        r = client.post(f"/api/collections/{nom}/publish", json=PUBLIER)
    assert r.status_code == 200
    erreur = r.json()["owui"]["error"]
    assert "socle injoignable" in erreur and "RuntimeError" in erreur and "réessayez" in erreur
