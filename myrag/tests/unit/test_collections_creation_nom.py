"""L'identifiant d'une collection se valide AU SERVEUR : c'est lui que tapent les applications.
(Constaté en production : une collection nommée « Test trajectoire écologie ».)"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import GROUPE_TESTEURS, personne


def _creer(client, name, partitions=(), **champs):
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.list_models = AsyncMock(return_value={"data": [{"id": f"openrag-{p}"} for p in partitions]})
        return client.post("/api/collections", json={"name": name, "scope": "group", "scope_groups": [GROUPE_TESTEURS], **champs})


@pytest.mark.parametrize("name,motif", [
    ("Test trajectoire écologie", "format"), ("demo-refusee", "prefixe"), ("ab", "longueur"), ("templates", "reserve"),
])
def test_un_identifiant_fautif_est_refuse_avec_son_motif(client, en_tant_que, name, motif):
    en_tant_que(personne(1))
    r = _creer(client, name)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["reason"] == motif and r.json()["detail"]["message"]


def test_la_casse_est_normalisee(client, en_tant_que, purger):
    purger("codes-essai-casse")
    en_tant_que(personne(1))
    r = _creer(client, "  Codes-Essai-Casse ", titre="Codes d'essai")
    assert r.status_code == 200 and r.json()["collection"]["name"] == "codes-essai-casse"
    assert r.json()["collection"]["titre"] == "Codes d'essai"
    purger("codes-essai-casse")


def test_rattacher_une_partition_existante_reste_possible_quel_que_soit_son_nom(client, en_tant_que, purger):
    """Le nom d'une partition déjà chez OpenRAG est un fait : on ne peut que l'adopter."""
    purger("rag-etranger-adoptee")
    en_tant_que(personne(1))
    assert _creer(client, "rag-etranger-adoptee").status_code == 422
    r = _creer(client, "rag-etranger-adoptee", partitions=["rag-etranger-adoptee"])
    assert r.status_code == 200 and r.json()["collection"]["name"] == "rag-etranger-adoptee"
    purger("rag-etranger-adoptee")


def test_check_name_dit_pourquoi(client, en_tant_que):
    en_tant_que(personne(1))
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.list_models = AsyncMock(return_value={"data": []})
        r = client.get("/api/collections/check-name", params={"name": "demo-x"}).json()
        libre = client.get("/api/collections/check-name", params={"name": "codes-jamais-pris"}).json()
    assert (r["available"], r["reason"]) == (False, "prefixe") and "contenu" in r["message"]
    assert libre == {"available": True}


def test_les_regles_sont_servies_au_formulaire(client, en_tant_que):
    en_tant_que(personne(1))
    r = client.get("/api/collections/regles-nommage").json()
    assert r["max"] == 40 and "demo-" in r["prefixes_bannis"] and r["motifs"]["prefixe"]
