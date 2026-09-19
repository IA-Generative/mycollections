"""La fiche d'une collection dans l'assistant : nom = titre, étiquette = catégorie, et une
resynchronisation qui ne peut être lancée que par l'administration."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.fiche_assistant import nom_de_fiche
from app.services.owui_client import fusionner_fiche
from tests.conftest import SUPERADMIN, personne


@pytest.mark.parametrize("alias,attendu", [
    ("", "Codes NATINF"),
    ("📚 amorce-natinf", "Codes NATINF"),            # l'ancien défaut du wizard
    ("MirAI amorce-natinf", "Codes NATINF"),          # l'ancien défaut de la page de publication
    ("📚 Nomenclature NATINF", "Nomenclature NATINF"),  # un vrai nom saisi : gardé, sans pictogramme
    ("Infractions — NATINF", "Infractions — NATINF"),
])
def test_le_nom_de_la_fiche_est_le_titre_sauf_nom_saisi(alias, attendu):
    assert nom_de_fiche({"name": "amorce-natinf", "titre": "Codes NATINF"}, alias) == attendu


def _publier(client, nom, **corps):
    with patch("app.services.owui_client.OwuiClient") as cls:
        cls.return_value.upsert_model = AsyncMock(return_value={"id": "ok"})
        r = client.post(f"/api/collections/{nom}/publish", json={"visibility": "group", **corps})
    assert r.status_code == 200, r.text
    return r.json(), cls.return_value.upsert_model


def test_publier_pose_le_titre_et_la_categorie(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, titre="Codes de test")
    en_tant_que(SUPERADMIN)
    client.put("/api/categories/affectations", json={"affectations": {nom: "securite-delinquance"}})
    rendu, upsert = _publier(client, nom)
    k = upsert.await_args.kwargs
    assert k["model_id"] == f"openrag-{nom}" and k["name"] == "Codes de test"
    assert k["tags"] == ["Sécurité et délinquance"] and "Droit des étrangers" in k["tags_geres"]
    assert rendu["nom_fiche"] == "Codes de test" and rendu["owui"]["synced"] is True
    assert rendu["alias_name"] == "", "rien n'a été saisi : le nom suivra le titre"


def test_la_description_saisie_est_gardee_d_une_ouverture_a_l_autre(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    _publier(client, nom, alias_description="Recherche dans les codes de test")
    assert client.get(f"/api/collections/{nom}/publication").json()["alias_description"] == "Recherche dans les codes de test"


def test_une_collection_en_verification_le_dit_dans_sa_fiche(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    _, upsert = _publier(client, nom, alias_description="Codes de test")
    assert upsert.await_args.kwargs["description"].startswith("⚠ ") and "Codes de test" in upsert.await_args.kwargs["description"]


def test_une_mention_perimee_n_est_pas_une_description_redigee():
    avant = {"meta": {"description": "⚠ en cours de vérification — vieux"}, "params": {}}
    voulue = {"meta": {"description": "Description de la fiche", "tags": []}, "params": {}}
    assert fusionner_fiche(avant, voulue)["meta"]["description"] == "Description de la fiche"


def test_changer_de_categorie_remplace_l_etiquette_sans_toucher_aux_autres():
    avant = {"params": {}, "meta": {"tags": [{"name": "Élus et vie publique"}, {"name": "Favoris DGEF"}, {"name": "Mes collections"}]}}
    voulue = {"params": {}, "meta": {"tags": [{"name": "Droit des étrangers"}, {"name": "Mes collections"}]}}
    f = fusionner_fiche(avant, voulue, tags_geres={"Élus et vie publique", "Droit des étrangers"})
    assert [t["name"] for t in f["meta"]["tags"]] == ["Favoris DGEF", "Droit des étrangers", "Mes collections"]


def test_resynchroniser_est_reserve_a_l_administration(client, en_tant_que):
    en_tant_que(personne(1))
    assert client.post("/api/publications/resynchroniser").status_code == 403


def test_resynchroniser_a_sec_n_ecrit_rien_et_dit_ce_qui_partirait(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, titre="Codes de test")
    _publier(client, nom)
    en_tant_que(SUPERADMIN)
    with patch("app.services.owui_client.OwuiClient") as cls:
        r = client.post("/api/publications/resynchroniser", params={"a_sec": "true"})
    cls.assert_not_called()
    fiche = next(f for f in r.json()["fiches"] if f["collection"] == nom)
    assert fiche == {"collection": nom, "model_id": f"openrag-{nom}", "nom": "Codes de test", "tags": [], "a_sec": True}


def test_un_nouveau_titre_atteint_la_fiche_a_la_resynchronisation(client, en_tant_que, creer_collection, nom):
    createur = personne("createur")
    creer_collection(nom, createur)
    _publier(client, nom)                       # nom de fiche = titre déduit de l'identifiant
    client.patch(f"/api/collections/{nom}", json={"titre": "Titre corrigé"})
    en_tant_que(SUPERADMIN)
    with patch("app.services.owui_client.OwuiClient") as cls:
        cls.return_value.upsert_model = AsyncMock(return_value={})
        r = client.post("/api/publications/resynchroniser")
    assert r.status_code == 200 and r.json()["echecs"] == []
    noms = {a.kwargs["model_id"]: a.kwargs["name"] for a in cls.return_value.upsert_model.await_args_list}
    assert noms[f"openrag-{nom}"] == "Titre corrigé"


def test_une_fiche_qui_echoue_n_arrete_pas_les_autres(client, en_tant_que, creer_collection, nom, purger):
    autre = nom[:34].rstrip("-") + "-bis"  # ≤ 40 caractères : un identifiant valide
    purger(autre)
    creer_collection(nom); _publier(client, nom)
    creer_collection(autre); _publier(client, autre)
    en_tant_que(SUPERADMIN)

    async def capricieux(**k):
        if k["model_id"] == f"openrag-{nom}":
            raise RuntimeError("socle indisponible")
        return {}
    with patch("app.services.owui_client.OwuiClient") as cls:
        cls.return_value.upsert_model = AsyncMock(side_effect=capricieux)
        bilan = client.post("/api/publications/resynchroniser").json()
    assert {e["collection"] for e in bilan["echecs"]} == {nom}
    assert autre in {f["collection"] for f in bilan["fiches"]}
    purger(autre)


def test_classer_conseille_de_resynchroniser(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(SUPERADMIN)
    r = client.put("/api/categories/affectations", json={"affectations": {nom: "droit-etrangers"}}).json()
    assert r["resync_conseillee"] is True
    assert client.put("/api/categories/affectations", json={"affectations": {nom: "droit-etrangers"}}).json()["resync_conseillee"] is False
