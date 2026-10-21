"""Aucune donnée personnelle en clair dans le réseau d'entraide : colonnes et réponses JSON."""

from __future__ import annotations

import re

from app.database import Base
from tests.conftest import personne
from tests.unit.test_regle1_usage_frequence import DEMANDE

INTERDITES = re.compile(r"(email|nom|prenom|telephone|contact)", re.I)
AUTORISES = re.compile(r"_(hash|chiffre)$")


def test_les_colonnes_entraide_sans_donnee_personnelle():
    tables = [t for t in Base.metadata.tables.values() if t.name.startswith("entraide_")]
    assert {t.name for t in tables} >= {"entraide_appel", "entraide_reponse", "entraide_lien"}
    for t in tables:
        for c in t.columns:
            assert not INTERDITES.search(c.name) or AUTORISES.search(c.name), f"{t.name}.{c.name}"


def _cles(valeur):
    if isinstance(valeur, dict):
        for k, v in valeur.items():
            yield k
            yield from _cles(v)
    elif isinstance(valeur, list):
        for v in valeur:
            yield from _cles(v)


def test_les_reponses_json_sans_ces_cles(client, en_tant_que):
    en_tant_que(personne("auteur"))
    appel = client.post("/api/entraide/appels", json={"type": "propose", "titre": "Je connais les marchés publics", "texte": "Écrivez-moi ici."}).json()["appel"]
    client.post(f"/api/entraide/appels/{appel['id']}/publier")
    client.post(f"/api/entraide/appels/{appel['id']}/reponses", json={"texte": "Merci"})
    en_tant_que(personne("autre"))
    client.post("/api/demandes", json=DEMANDE)
    corps = [client.get("/api/entraide").json(), client.get(f"/api/entraide/appels/{appel['id']}").json()]
    cles = set(_cles(corps))
    assert not [k for k in cles if INTERDITES.search(k) and not AUTORISES.search(k)], cles
    assert "auteur_hash" not in cles
