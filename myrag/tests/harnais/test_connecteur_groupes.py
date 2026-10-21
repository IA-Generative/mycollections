"""Un connecteur réservé à des groupes (`groupes` dans sa déclaration) : seules les personnes de
ces groupes le lisent, le voient dans la liste des sources et l'interrogent ; un claim en noms
courts ne donne aucun droit ; l'administration lit tout ; sans `groupes`, ouvert à tous."""

from __future__ import annotations

import json

import pytest

from app.config import settings
from app.harnais import perimetre
from app.harnais.contrat import FicheAssistant
from app.services import connecteurs_declares
from tests.conftest import SUPERADMIN

GROUPE = "/g/experimentation-exemple"


def declaration(**modifs) -> dict:
    d = {"id": "referentiel-exemple", "type": "eligibilite", "url": "http://referentiel.fake-domain.name", "titre": "Référentiel d'exemple", "tables": ["titres"]}
    return {**d, **modifs}


@pytest.fixture
def declarer(monkeypatch):
    def _f(*entrees) -> None:
        monkeypatch.setattr(settings, "connecteurs", json.dumps(list(entrees)))

    return _f


def test_sans_groupes_ouvert_a_tous(declarer):
    declarer(declaration())
    assert set(connecteurs_declares.lisibles_par(["/g/autre"])) == {"referentiel-exemple"}


def test_reserve_aux_membres_du_groupe(declarer):
    declarer(declaration(groupes=[GROUPE]))
    assert set(connecteurs_declares.lisibles_par([GROUPE, "/g/autre"])) == {"referentiel-exemple"}
    assert connecteurs_declares.lisibles_par(["/g/autre"]) == {}
    assert connecteurs_declares.lisibles_par([]) == {}
    assert set(connecteurs_declares.lisibles_par(SUPERADMIN.groups)) == {"referentiel-exemple"}, "l'administration lit tout"


def test_un_claim_en_noms_courts_ne_donne_aucun_droit(declarer):
    declarer(declaration(groupes=[GROUPE]))
    assert connecteurs_declares.lisibles_par(["experimentation-exemple", GROUPE]) == {}


def test_un_groupe_qui_n_est_pas_un_chemin_rend_la_declaration_invalide(declarer):
    declarer(declaration(groupes=["experimentation-exemple"]))
    assert connecteurs_declares.declarations() == {}


def test_le_perimetre_d_un_assistant_suit_les_groupes(declarer):
    declarer(declaration(groupes=[GROUPE]))
    fiche = FicheAssistant.model_validate(
        {"assistant": "assistant-exemple", "titre": "Assistant d'exemple", "sources": [{"id": "referentiel-exemple", "type": "connecteur", "regime": "toujours", "rang": 1}]}
    )

    def lisibles(groupes):
        return perimetre.sources_lisibles(fiche, {}, groupes=groupes, sub="s", connecteurs=connecteurs_declares.lisibles_par(groupes))

    assert lisibles([GROUPE]) == ["referentiel-exemple"]
    assert lisibles(["/g/autre"]) == [], "témoin négatif : hors du groupe, le connecteur n'est pas interrogé"


def test_la_liste_des_connecteurs_suit_les_groupes(client, en_tant_que, declarer):
    from tests.conftest import personne

    declarer(declaration(groupes=[GROUPE]))
    en_tant_que(personne("membre", GROUPE))
    assert [c["id"] for c in client.get("/api/assistants/connecteurs").json()["connecteurs"]] == ["referentiel-exemple"]
    en_tant_que(personne("autre"))
    assert client.get("/api/assistants/connecteurs").json()["connecteurs"] == []
