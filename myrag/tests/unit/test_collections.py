"""Fiche d'une collection et consignes (prompt système), lues et écrites en base.

Réécrit le 2026-10-04 : la version précédente déposait un `metadata.json` sur disque,
un stockage abandonné depuis le passage à la base ; elle ne pouvait plus réussir.
"""

from unittest.mock import AsyncMock, patch

from tests.conftest import SUPERADMIN, personne


def test_creer_puis_relire_une_collection(client, en_tant_que, creer_collection, nom):
    cree = creer_collection(nom, description="Essai", strategy="auto", sensitivity="public")
    assert cree["name"] == nom
    assert cree["system_prompt"], "la création doit poser des consignes par défaut"
    en_tant_que(personne("createur"))
    r = client.get(f"/api/collections/{nom}")
    assert r.status_code == 200 and r.json()["name"] == nom


def test_la_liste_contient_la_collection_creee(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.list_models = AsyncMock(return_value={"data": []})
        cls.return_value.list_files = AsyncMock(return_value=[])
        r = client.get("/api/collections")
    assert r.status_code == 200
    assert nom in [c["name"] for c in r.json()["collections"]]


def test_une_collection_inconnue_rend_404(client, en_tant_que):
    en_tant_que(SUPERADMIN)
    assert client.get("/api/collections/inconnue-de-tous").status_code == 404


def test_consignes_lues_puis_modifiees_par_le_gestionnaire(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    createur = en_tant_que(personne("createur"))
    lu = client.get(f"/api/collections/{nom}/system-prompt")
    assert lu.status_code == 200 and lu.json()["source"] == "collection"
    r = client.patch(f"/api/collections/{nom}/system-prompt", json={"system_prompt": "Nouveau prompt juridique."})
    assert r.status_code == 200, r.text
    en_tant_que(createur)
    assert client.get(f"/api/collections/{nom}/system-prompt").json()["system_prompt"] == "Nouveau prompt juridique."


def test_consignes_par_defaut_pour_une_collection_sans_fiche(client, en_tant_que):
    en_tant_que(SUPERADMIN)
    r = client.get("/api/collections/sans-fiche-aucune/system-prompt")
    assert r.status_code == 200
    assert r.json()["source"] == "default" and r.json()["template"] == "generic"


def test_un_simple_lecteur_ne_modifie_pas_les_consignes(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("simple-lecteur"))
    r = client.patch(f"/api/collections/{nom}/system-prompt", json={"system_prompt": "x"})
    assert r.status_code == 403
