"""Les rubriques du catalogue : tout le monde lit, seul un superadmin règle — catégories
ET classement, à chaud."""

import os
import sqlite3

import pytest

from tests.conftest import SUPERADMIN, personne


def _sql(requete, params=()):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        lignes = con.execute(requete, params).fetchall()
        con.commit()
        return lignes
    finally:
        con.close()


@pytest.fixture
def cle(request):
    k = ("t-" + request.node.name.lower().replace("_", "-"))[:60]
    _sql("UPDATE collections SET categorie = NULL WHERE categorie = ?", (k,))
    _sql("DELETE FROM categories WHERE cle = ?", (k,))
    yield k
    _sql("UPDATE collections SET categorie = NULL WHERE categorie = ?", (k,))
    _sql("DELETE FROM categories WHERE cle = ?", (k,))


def test_les_rubriques_de_depart_sont_semees_et_lisibles_de_tous(client, en_tant_que):
    en_tant_que(personne(1))
    r = client.get("/api/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert {"droit-etrangers", "securite-delinquance", "guides-demonstrations"} <= {c["cle"] for c in cats}
    assert [c["ordre"] for c in cats] == sorted(c["ordre"] for c in cats)
    assert all("nb_collections" in c and c["libelle"] for c in cats)


@pytest.mark.parametrize("methode,chemin,corps", [
    ("post", "/api/categories", {"cle": "pirate", "libelle": "Pirate"}),
    ("patch", "/api/categories/droit-etrangers", {"libelle": "Pirate"}),
    ("delete", "/api/categories/droit-etrangers", None),
    ("put", "/api/categories/ordre", {"cles": []}),
    ("put", "/api/categories/affectations", {"affectations": {}}),
])
def test_regler_les_rubriques_est_reserve_a_l_administration(client, en_tant_que, methode, chemin, corps):
    en_tant_que(personne(1))
    r = client.request(methode.upper(), chemin, json=corps)
    assert r.status_code == 403, r.text
    assert "droit-etrangers" in {c["cle"] for c in client.get("/api/categories").json()["categories"]}


def test_creer_modifier_supprimer(client, en_tant_que, cle):
    en_tant_que(SUPERADMIN)
    r = client.post("/api/categories", json={"cle": cle, "libelle": "Ressources humaines", "description": "Paie, congés"})
    assert r.status_code == 201, r.text
    assert client.post("/api/categories", json={"cle": cle, "libelle": "Doublon"}).status_code == 409
    assert client.patch(f"/api/categories/{cle}", json={"libelle": "RH"}).json()["categorie"]["libelle"] == "RH"
    # La description n'était pas dans le PATCH : elle n'a pas bougé.
    assert next(c for c in client.get("/api/categories").json()["categories"] if c["cle"] == cle)["description"] == "Paie, congés"
    assert client.delete(f"/api/categories/{cle}").status_code == 200
    assert client.delete(f"/api/categories/{cle}").status_code == 404
    assert client.patch(f"/api/categories/{cle}", json={"libelle": "RH"}).status_code == 404


@pytest.mark.parametrize("mauvaise", ["droit_etrangers", "-x", "a--b", "droit étrangers"])
def test_une_cle_mal_formee_est_refusee(client, en_tant_que, mauvaise):
    en_tant_que(SUPERADMIN)
    assert client.post("/api/categories", json={"cle": mauvaise, "libelle": "Peu importe"}).status_code == 422


def test_classer_une_collection_et_le_lire_dans_le_catalogue(client, en_tant_que, creer_collection, nom, cle):
    creer_collection(nom, titre="Codes de test")
    en_tant_que(SUPERADMIN)
    client.post("/api/categories", json={"cle": cle, "libelle": "Essais"})
    r = client.put("/api/categories/affectations", json={"affectations": {nom: cle}})
    assert r.status_code == 200 and r.json()["changees"] == [nom], r.text
    assert next(c for c in r.json()["categories"] if c["cle"] == cle)["nb_collections"] == 1
    fiche = client.get(f"/api/collections/{nom}").json()
    assert fiche["categorie"] == cle and fiche["titre"] == "Codes de test"
    # Rejouer ne change rien et n'écrit rien de plus au journal.
    assert client.put("/api/categories/affectations", json={"affectations": {nom: cle}}).json()["inchangees"] == [nom]
    types = [e["type"] for e in client.get(f"/api/collections/{nom}/journal").json()["evenements"]]
    assert types.count("categorie.changee") == 1


def test_supprimer_une_rubrique_declasse_ses_collections(client, en_tant_que, creer_collection, nom, cle):
    creer_collection(nom)
    en_tant_que(SUPERADMIN)
    client.post("/api/categories", json={"cle": cle, "libelle": "Éphémère"})
    client.put("/api/categories/affectations", json={"affectations": {nom: cle}})
    r = client.delete(f"/api/categories/{cle}")
    assert r.json()["collections_declassees"] == 1
    assert client.get(f"/api/collections/{nom}").json()["categorie"] is None


def test_une_rubrique_ou_une_collection_inconnue_n_ecrit_rien(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(SUPERADMIN)
    assert client.put("/api/categories/affectations", json={"affectations": {nom: "n-existe-pas"}}).status_code == 404
    r = client.put("/api/categories/affectations", json={"affectations": {nom: "droit-etrangers", "fantome-xyz": "droit-etrangers"}})
    assert r.status_code == 404 and "fantome-xyz" in r.json()["detail"]
    assert client.get(f"/api/collections/{nom}").json()["categorie"] is None, "le lot entier est annulé"


def test_le_proprietaire_regle_le_titre_mais_pas_la_rubrique(client, en_tant_que, creer_collection, nom):
    createur = personne("createur")
    creer_collection(nom, createur)
    r = client.patch(f"/api/collections/{nom}", json={"titre": "Mon beau titre", "categorie": "droit-etrangers"})
    assert r.status_code == 200, r.text
    fiche = client.get(f"/api/collections/{nom}").json()
    assert fiche["titre"] == "Mon beau titre" and fiche["categorie"] is None


def test_l_ordre_se_regle_et_les_absentes_passent_apres(client, en_tant_que):
    en_tant_que(SUPERADMIN)
    avant = [c["cle"] for c in client.get("/api/categories").json()["categories"]]
    try:
        r = client.put("/api/categories/ordre", json={"cles": [avant[-1], avant[0]]})
        assert r.status_code == 200
        apres = [c["cle"] for c in r.json()["categories"]]
        assert apres[:2] == [avant[-1], avant[0]] and sorted(apres) == sorted(avant)
        assert client.put("/api/categories/ordre", json={"cles": ["n-existe-pas"]}).status_code == 404
    finally:
        client.put("/api/categories/ordre", json={"cles": avant})
