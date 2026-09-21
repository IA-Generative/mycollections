"""Règle 1 — une demande porte un usage et une fréquence, jamais un score.

Et, décision PO du 2026-09-13 : elle dit comment la personne se procure la donnée
aujourd'hui — sans quoi elle n'est pas déposée. Décision PO du 2026-09-21 : l'auteur est
TOUJOURS joignable pour sa demande (ce n'est plus une question) — le formulaire web exige
son courriel, qui ne se lit que par le garant et l'administration.
"""

import pytest

from tests.conftest import personne

DEMANDE = {
    "titre": "Répertoire national des élus",
    "usage": "Vérifier la qualité d'élu d'un signataire avant réponse.",
    "frequence": "hebdomadaire",
    "service": "Préfecture — bureau du courrier",
    "acces_actuel": "Extraction CSV trimestrielle sur data.gouv.fr, recherche à la main.",
    "contact": "auteur@interieur.gouv.fr",
}


def test_une_demande_complete_est_creee(client, en_tant_que):
    en_tant_que(personne(1))
    r = client.post("/api/demandes", json=DEMANDE)
    assert r.status_code == 201, r.text
    d = r.json()["demande"]
    assert d["etat"] == "ouverte" and d["seuil"] == 5 and d["nb_soutiens"] == 0


@pytest.mark.parametrize("champ", ["score", "note", "priorite"])
def test_un_score_est_refuse(client, en_tant_que, champ):
    en_tant_que(personne(1))
    r = client.post("/api/demandes", json={**DEMANDE, champ: 3})
    assert r.status_code == 422


@pytest.mark.parametrize("champ", ["usage", "frequence", "titre"])
def test_usage_et_frequence_sont_obligatoires(client, en_tant_que, champ):
    en_tant_que(personne(1))
    corps = {k: v for k, v in DEMANDE.items() if k != champ}
    assert client.post("/api/demandes", json=corps).status_code == 422
    assert client.post("/api/demandes", json={**DEMANDE, champ: "   "}).status_code == 422


def test_une_frequence_hors_liste_est_refusee(client, en_tant_que):
    en_tant_que(personne(1))
    assert client.post("/api/demandes", json={**DEMANDE, "frequence": "souvent"}).status_code == 422


def test_sans_acces_actuel_la_demande_n_est_pas_deposee(client, en_tant_que):
    en_tant_que(personne(1))
    r = client.post("/api/demandes", json={**DEMANDE, "acces_actuel": ""})
    assert r.status_code == 422
    assert "procurez" in r.text and "impossible" in r.text
    corps = {k: v for k, v in DEMANDE.items() if k != "acces_actuel"}
    assert client.post("/api/demandes", json=corps).status_code == 422


def test_le_courriel_de_l_auteur_est_exige_au_depot(client, en_tant_que):
    en_tant_que(personne(1))
    corps = {k: v for k, v in DEMANDE.items() if k != "contact"}
    r = client.post("/api/demandes", json=corps)
    assert r.status_code == 422 and "courriel" in r.text and "garant" in r.text
    assert client.post("/api/demandes", json={**DEMANDE, "contact": "pas-un-courriel"}).status_code == 422


def test_la_question_du_recontact_n_est_plus_posee(client, en_tant_que):
    en_tant_que(personne(1))
    corps = {k: v for k, v in DEMANDE.items() if k != "recontact"}
    assert client.post("/api/demandes", json=corps).status_code == 201


def test_un_contact_explicitement_refuse_reste_refuse(client, en_tant_que):
    """Un client qui envoie encore « recontact: false » avec un courriel : on ne garde pas ce
    qu'il dit ne pas vouloir donner (la contrainte en base le garantit aussi)."""
    en_tant_que(personne(1))
    assert client.post("/api/demandes", json={**DEMANDE, "recontact": False}).status_code == 422


def test_le_courriel_ne_se_lit_que_par_le_garant_et_l_administration(client, en_tant_que):
    from tests.conftest import SUPERADMIN
    en_tant_que(personne(1))
    r = client.post("/api/demandes", json={**DEMANDE, "contact": "eric@interieur.gouv.fr"})
    assert r.status_code == 201 and "eric@" not in r.text
    ident = r.json()["demande"]["id"]
    en_tant_que(personne(2))
    assert "eric@" not in client.get(f"/api/demandes/{ident}").text   # un soutien quelconque : non
    assert "eric@" not in client.get("/api/demandes").text            # la liste : jamais
    client.post(f"/api/demandes/{ident}/soutenir", json={"role": "garant"})
    assert client.get(f"/api/demandes/{ident}").json()["demande"]["contact_auteur"] == "eric@interieur.gouv.fr"
    en_tant_que(SUPERADMIN)
    assert client.get(f"/api/demandes/{ident}").json()["demande"]["contact_auteur"] == "eric@interieur.gouv.fr"


def test_aucune_cle_de_score_dans_les_reponses(client, en_tant_que):
    en_tant_que(personne(1))
    client.post("/api/demandes", json=DEMANDE)
    liste = client.get("/api/demandes").json()["demandes"]
    assert liste
    for d in liste:
        assert not ({"score", "note", "priorite"} & set(d))
