"""L'étape 4 de l'assistant de création, figée côté serveur : une question saisie entre
« à relire » (brut) sauf si le client la dit validée ; « fiable » exige une question validée.
Le lot E réécrit l'écran ; ces règles restent."""

from __future__ import annotations

from tests.conftest import personne

URL = "/api/collections/{}/qualite/questions"


def test_relecture_par_defaut_puis_fiable(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    brut = client.post(URL.format(nom), json={"question": "Quel est le délai ?", "reponse": "Deux mois."})
    assert brut.status_code == 201, brut.text
    q = brut.json()["question"]
    assert q["relecture"] == "brut" and q["fiable"] is False and q["origine"] == "saisie"
    assert client.patch(URL.format(nom) + f"/{q['id']}", json={"fiable": True}).status_code == 409
    valide = client.post(URL.format(nom), json={"question": "Quelle pièce fournir ?", "reponse": "Un justificatif.", "relecture": "valide"})
    assert valide.status_code == 201 and valide.json()["question"]["relecture"] == "valide"
