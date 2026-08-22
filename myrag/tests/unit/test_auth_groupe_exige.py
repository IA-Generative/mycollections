"""Restriction d'accès à un groupe du realm (MYRAG_GROUPE_EXIGE).

Le claim `groups` porte le NOM FEUILLE des groupes, pas leur chemin : c'est la forme
qu'émet le mapper Keycloak en `full.path=false`. Ces tests fixent cette convention —
la panacher donnerait un refus permanent qu'aucun message n'expliquerait.
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


def test_chemin_complet_ne_vaut_pas_nom_feuille(groupe_exige):
    """Un claim en chemin (`full.path=true`) ne satisfait PAS la règle : le dispositif
    exige une seule forme, et le mapper de la bêta émet le nom feuille."""
    with pytest.raises(HTTPException):
        _exiger_le_groupe({"groups": ["/g/mirai-beta-testeurs"]})


def test_claim_non_liste_tolere(groupe_exige):
    _exiger_le_groupe({"groups": "mirai-beta-testeurs"})
