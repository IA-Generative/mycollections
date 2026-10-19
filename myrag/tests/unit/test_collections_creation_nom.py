"""L'identifiant d'une collection se valide AU SERVEUR : c'est lui que tapent les applications.
(Constaté en production : une collection nommée « Test trajectoire écologie ».)"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.openrag_client import ListeModeles, ModeleOpenRAG
from tests.conftest import GROUPE_TESTEURS, personne


def _creer(client, name, partitions=(), **champs):
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.list_models = AsyncMock(return_value=ListeModeles(data=[ModeleOpenRAG(id=f"openrag-{p}") for p in partitions]))
        return client.post("/api/collections", json={"name": name, "scope": "group", "scope_groups": [GROUPE_TESTEURS], **champs})


@pytest.mark.parametrize(
    "name,motif",
    [
        ("Test trajectoire écologie", "format"),
        ("demo-refusee", "prefixe"),
        ("ab", "longueur"),
        ("templates", "reserve"),
    ],
)
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
        cls.return_value.list_models = AsyncMock(return_value=ListeModeles(data=[]))
        r = client.get("/api/collections/check-name", params={"name": "demo-x"}).json()
        libre = client.get("/api/collections/check-name", params={"name": "codes-jamais-pris"}).json()
    assert (r["available"], r["reason"]) == (False, "prefixe") and "contenu" in r["message"]
    assert libre == {"available": True}


def test_les_regles_sont_servies_au_formulaire(client, en_tant_que):
    en_tant_que(personne(1))
    r = client.get("/api/collections/regles-nommage").json()
    assert r["max"] == 40 and "demo-" in r["prefixes_bannis"] and r["motifs"]["prefixe"]


# --- La catégorie choisie à la création (étape 2 de l'assistant) ---


def test_une_categorie_connue_est_acceptee(client, en_tant_que, nom):
    en_tant_que(personne(1))
    r = _creer(client, nom, categorie="textes-reference")
    assert r.status_code == 200, r.text
    assert r.json()["collection"]["categorie"] == "textes-reference"


def test_une_categorie_inconnue_est_refusee(client, en_tant_que, nom):
    en_tant_que(personne(1))
    r = _creer(client, nom, categorie="rubrique-inventee")
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "categorie"
    en_tant_que(personne(1))
    assert client.get(f"/api/collections/{nom}").status_code == 404, "rien n'est créé"


def test_sans_categorie_la_collection_est_non_classee(client, en_tant_que, nom):
    en_tant_que(personne(1))
    r = _creer(client, nom)
    assert r.status_code == 200 and r.json()["collection"]["categorie"] is None


def test_qui_gere_reclasse_dans_les_reglages_un_lecteur_non(client, en_tant_que, nom):
    createur = personne("createur-classement")
    en_tant_que(createur)
    assert _creer(client, nom, categorie="textes-reference").status_code == 200
    r = client.patch(f"/api/collections/{nom}", json={"categorie": "ressources-internes"})
    assert r.status_code == 200 and r.json()["categorie"] == "ressources-internes"
    assert client.patch(f"/api/collections/{nom}", json={"categorie": "rubrique-inventee"}).status_code == 422
    assert client.patch(f"/api/collections/{nom}", json={"categorie": None}).json()["categorie"] is None
    en_tant_que(personne("simple-lecteur-classement"))
    assert client.patch(f"/api/collections/{nom}", json={"categorie": "textes-reference"}).status_code == 403


def test_l_administration_reclasse_toujours(client, en_tant_que, nom):
    from tests.conftest import SUPERADMIN

    en_tant_que(personne(1))
    assert _creer(client, nom, categorie="textes-reference").status_code == 200
    en_tant_que(SUPERADMIN)
    r = client.put("/api/categories/affectations", json={"affectations": {nom: "guides-demonstrations"}})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/collections/{nom}").json()["categorie"] == "guides-demonstrations"
