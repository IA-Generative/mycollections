"""Les demandes de la communauté, figées : forme des réponses et parcours, pour que le
réseau d'entraide (lot G) les laisse telles quelles — y compris quand un drapeau `entraide`
est posé."""

from __future__ import annotations

from tests.conftest import personne
from tests.non_regression._outils import figer, forme
from tests.unit.test_regle1_usage_frequence import DEMANDE


def _parcours(client, en_tant_que) -> dict:
    en_tant_que(personne("auteur"))
    r = client.post("/api/demandes", json=DEMANDE)
    assert r.status_code == 201, r.text
    creee = r.json()
    ident = creee["demande"]["id"]
    en_tant_que(personne("garant"))
    soutien = client.post(f"/api/demandes/{ident}/soutenir", json={"role": "garant"})
    assert soutien.status_code == 200, soutien.text
    en_tant_que(personne("auteur"))
    return {
        "creation": forme(creee),
        "liste": forme(client.get("/api/demandes").json()),
        "lecture": forme(client.get(f"/api/demandes/{ident}").json()),
        "soutien": forme(soutien.json()),
        "journal": forme(client.get(f"/api/demandes/{ident}/journal").json()),
        "etats": {"apres_creation": creee["demande"]["etat"], "apres_garant": soutien.json()["demande"]["etat"]},
    }


def test_parcours_d_une_demande(client, en_tant_que):
    figer("demandes/parcours", _parcours(client, en_tant_que))


def test_un_drapeau_entraide_ne_change_rien_aux_demandes(client, en_tant_que, capacites):
    capacites(demandes=True, entraide=True)
    figer("demandes/parcours", _parcours(client, en_tant_que))


def test_demandes_desactivees_404(client, en_tant_que, capacites):
    capacites(demandes=False)
    en_tant_que(personne(1))
    assert client.get("/api/demandes").status_code == 404
    assert client.post("/api/demandes", json=DEMANDE).status_code == 404
