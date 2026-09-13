"""Règle 4 — proposer est ouvert à tout utilisateur authentifié ; publier et refuser
sont réservés au garant ; un refus est motivé ; tout garde un historique."""

from tests.conftest import SUPERADMIN, personne

GARANT = personne("garant")
PROPOSITION = {
    "cible_type": "ligne", "cible_ref": "NATINF 7987 · libellé",
    "avant": "Conduite d'un véhicule sans permis",
    "apres": "Conduite d'un véhicule sans être titulaire du permis correspondant",
    "justification": "Le libellé court prête à confusion avec la conduite malgré suspension.",
}


def _proposer(client, en_tant_que, nom, qui=None, **extra):
    en_tant_que(qui or personne("contributrice"))
    return client.post(f"/api/collections/{nom}/propositions", json={**PROPOSITION, **extra})


def test_un_simple_authentifie_propose(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    r = _proposer(client, en_tant_que, nom)
    assert r.status_code == 201, r.text
    p = r.json()["proposition"]
    assert p["etat"] == "proposee" and p["source"] is None


def test_justification_obligatoire_source_facultative(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    assert _proposer(client, en_tant_que, nom, justification="").status_code == 422
    assert _proposer(client, en_tant_que, nom, source="https://natinfo.app/natinf/7987").status_code == 201


def test_publier_est_reserve_au_garant(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    ident = _proposer(client, en_tant_que, nom).json()["proposition"]["id"]
    en_tant_que(personne("autre"))
    assert client.post(f"/api/collections/{nom}/propositions/{ident}/publier").status_code == 403
    en_tant_que(GARANT)
    r = client.post(f"/api/collections/{nom}/propositions/{ident}/publier")
    assert r.status_code == 200 and r.json()["proposition"]["etat"] == "publiee"


def test_un_superadmin_peut_publier(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    ident = _proposer(client, en_tant_que, nom).json()["proposition"]["id"]
    en_tant_que(SUPERADMIN)
    assert client.post(f"/api/collections/{nom}/propositions/{ident}/publier").status_code == 200


def test_un_refus_porte_un_motif(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    ident = _proposer(client, en_tant_que, nom).json()["proposition"]["id"]
    en_tant_que(GARANT)
    assert client.post(f"/api/collections/{nom}/propositions/{ident}/refuser", json={"motif": " "}).status_code == 422
    r = client.post(f"/api/collections/{nom}/propositions/{ident}/refuser", json={"motif": "code abrogé, mais cité en procédure"})
    assert r.status_code == 200 and r.json()["proposition"]["motif_refus"].startswith("code abrogé")


def test_l_historique_suit_la_proposition(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    ident = _proposer(client, en_tant_que, nom).json()["proposition"]["id"]
    en_tant_que(GARANT)
    client.post(f"/api/collections/{nom}/propositions/{ident}/publier")
    fiche = client.get(f"/api/collections/{nom}/propositions/{ident}").json()
    types = [e["type"] for e in fiche["historique"]]
    assert types == ["proposition.publiee", "proposition.deposee"]
    assert fiche["proposition"]["avant"] == PROPOSITION["avant"]


def test_une_decision_ne_se_prend_qu_une_fois(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    ident = _proposer(client, en_tant_que, nom).json()["proposition"]["id"]
    en_tant_que(GARANT)
    client.post(f"/api/collections/{nom}/propositions/{ident}/publier")
    assert client.post(f"/api/collections/{nom}/propositions/{ident}/refuser", json={"motif": "trop tard"}).status_code == 409


def test_un_signalement_porte_un_motif_de_la_liste(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, GARANT)
    en_tant_que(personne("lectrice"))
    assert client.post(f"/api/collections/{nom}/signalements", json={"motif": "bof", "texte": "x"}).status_code == 422
    r = client.post(f"/api/collections/{nom}/signalements", json={"motif": "obsolete", "texte": "Annulé par le CE le 2 juin 2025."})
    assert r.status_code == 201 and r.json()["signalement"]["etat"] == "ouvert"
    ident = r.json()["signalement"]["id"]
    assert client.post(f"/api/collections/{nom}/signalements/{ident}/traiter", json={"etat": "clos"}).status_code == 403
    en_tant_que(GARANT)
    assert client.post(f"/api/collections/{nom}/signalements/{ident}/traiter", json={"etat": "clos"}).status_code == 200
