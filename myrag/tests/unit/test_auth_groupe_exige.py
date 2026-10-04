"""Restriction d'accès à un groupe du realm (MYRAG_GROUPE_EXIGE).

Deux formes d'entrée : un nom court (hérité du mapper `full.path=false`, comparé tel
quel) ou un chemin (`full.path=true`, la forme sûre). Une liste séparée par des virgules
accepte les deux le temps de basculer le mapper.
"""

import pytest
from fastapi import HTTPException

import app.config
from app.auth import _exiger_le_groupe


@pytest.fixture
def groupe_exige(monkeypatch):
    monkeypatch.setattr(app.config.settings, "myrag_groupe_exige", "mirai-beta-testeurs")


def test_sans_restriction_tout_passe(monkeypatch):
    monkeypatch.setattr(app.config.settings, "myrag_groupe_exige", "")
    _exiger_le_groupe({})  # ne lève pas


def test_membre_du_groupe_passe(groupe_exige):
    _exiger_le_groupe({"groups": ["autre-chose", "mirai-beta-testeurs"]})


def test_hors_groupe_refuse(groupe_exige):
    with pytest.raises(HTTPException) as e:
        _exiger_le_groupe({"groups": ["une-autre-communaute"]})
    assert e.value.status_code == 403


def test_jeton_sans_claim_groups_refuse(groupe_exige):
    with pytest.raises(HTTPException) as e:
        _exiger_le_groupe({})
    assert e.value.status_code == 403


def test_chemin_complet_ne_vaut_pas_nom_court(groupe_exige):
    """Une entrée en nom court ne compare pas les feuilles des chemins : sinon
    `/g/n-importe-quoi/mirai-beta-testeurs`, créé dans keycloak-comu, passerait."""
    with pytest.raises(HTTPException):
        _exiger_le_groupe({"groups": ["/g/mirai-beta-testeurs"]})


@pytest.fixture
def chemin_exige(monkeypatch):
    monkeypatch.setattr(app.config.settings, "myrag_groupe_exige", "/g/mirai-beta-testeurs")


def test_chemin_exige_passe(chemin_exige):
    _exiger_le_groupe({"groups": ["/g/autre", "/g/mirai-beta-testeurs"]})


def test_chemin_exige_homonyme_refuse(chemin_exige):
    with pytest.raises(HTTPException) as e:
        _exiger_le_groupe({"groups": ["/g/equipe/mirai-beta-testeurs"]})
    assert e.value.status_code == 403


def test_chemin_exige_refuse_un_claim_en_noms_courts(chemin_exige):
    """En noms courts, un groupe NOMMÉ « /g/mirai-beta-testeurs » imiterait le chemin :
    le claim porte aussi des noms sans « / », il est écarté en bloc."""
    with pytest.raises(HTTPException):
        _exiger_le_groupe({"groups": ["Admins", "/g/mirai-beta-testeurs"]})


def test_bascule_les_deux_formes_passent(monkeypatch):
    monkeypatch.setattr(app.config.settings, "myrag_groupe_exige",
                        " mirai-beta-testeurs , /g/mirai-beta-testeurs ")
    _exiger_le_groupe({"groups": ["mirai-beta-testeurs", "Admins"]})
    _exiger_le_groupe({"groups": ["/g/mirai-beta-testeurs", "/g/BACI/Admins"]})
    with pytest.raises(HTTPException):
        _exiger_le_groupe({"groups": ["/g/autre"]})


def test_claim_non_liste_tolere(groupe_exige):
    _exiger_le_groupe({"groups": "mirai-beta-testeurs"})
