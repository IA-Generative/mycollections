"""Règle 5 — aucun bouton si le service ne sait pas le faire : le serveur le tient
aussi (404), et lit le seuil chez le menu, avec cache, repli et jamais de blocage."""

import httpx
import pytest

from app.services import capacites
from tests.conftest import personne
from tests.unit.test_regle1_usage_frequence import DEMANDE


def test_demandes_desactivees_rend_404(client, en_tant_que, capacites):
    capacites(demandes=False)
    en_tant_que(personne(1))
    assert client.post("/api/demandes", json=DEMANDE).status_code == 404
    assert client.get("/api/demandes").status_code == 404


def test_signalements_desactives_rend_404(client, en_tant_que, creer_collection, nom, capacites):
    creer_collection(nom)
    capacites(signalements=False)
    en_tant_que(personne(2))
    assert client.post(f"/api/collections/{nom}/signalements", json={"motif": "erreur", "texte": "x"}).status_code == 404


def test_api_config_reflete_les_capacites(client, capacites):
    capacites(seuil_chantier=7, demandes=True)
    c = client.get("/api/config").json()
    assert c["seuil_chantier"] == 7 and c["demandes"] is True


SANS_RIEN = {"demandes": False, "signalements": False, "assistants": False, "entraide": False, "resana": False, "seuil_chantier": 5}


def _reponse(json):
    return httpx.Response(200, json=json, request=httpx.Request("GET", "http://menu.test"))


class TestLaLectureChezLeMenu:
    @pytest.fixture(autouse=True)
    def _url(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "capacites_url", "http://menu.test/_beta/capacites.json")
        capacites.oublier()
        yield
        capacites.oublier()

    def test_sans_url_les_defauts_n_activent_rien(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "capacites_url", "")
        assert capacites._lire_depuis_le_menu() == SANS_RIEN

    def test_seul_true_active(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **k: _reponse({"demandes": "oui", "signalements": True, "seuil_chantier": 3}))
        v = capacites._lire_depuis_le_menu()
        assert v["demandes"] is False and v["signalements"] is True and v["seuil_chantier"] == 3

    def test_un_seuil_absurde_est_ignore(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **k: _reponse({"seuil_chantier": 0}))
        assert capacites._lire_depuis_le_menu()["seuil_chantier"] == 5

    def test_menu_muet_garde_la_derniere_valeur_puis_les_defauts(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **k: _reponse({"demandes": True, "seuil_chantier": 4}))
        assert capacites._lire_depuis_le_menu()["seuil_chantier"] == 4

        def _panne(*a, **k):
            raise httpx.ConnectError("refusé")

        monkeypatch.setattr(httpx, "get", _panne)
        capacites._cache["expire"] = 0.0  # le cache a expiré, le menu ne répond plus
        assert capacites._lire_depuis_le_menu()["seuil_chantier"] == 4, "dernière valeur connue"
        capacites.oublier()
        assert capacites._lire_depuis_le_menu() == SANS_RIEN


class TestLaSurchargeDeLEnvironnement:
    @pytest.fixture(autouse=True)
    def _sans_menu(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "capacites_url", "")
        capacites.oublier()
        yield
        capacites.oublier()

    def test_elle_allume_une_fonction_sans_toucher_au_reste(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "capacites_surcharge", '{"assistants": true, "seuil_chantier": 3}')
        assert capacites._lire_depuis_le_menu() == {**SANS_RIEN, "assistants": True, "seuil_chantier": 3}

    def test_elle_passe_par_dessus_le_menu(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "capacites_url", "http://menu.test/_beta/capacites.json")
        monkeypatch.setattr(httpx, "get", lambda *a, **k: _reponse({"demandes": True, "signalements": True}))
        monkeypatch.setattr(settings, "capacites_surcharge", '{"signalements": false, "entraide": true}')
        v = capacites._lire_depuis_le_menu()
        assert v["demandes"] is True and v["signalements"] is False and v["entraide"] is True and v["assistants"] is False

    @pytest.mark.parametrize("brut", ["pas du json", "[1, 2]", '{"assistants": "oui"}'])
    def test_illisible_ou_douteuse_elle_n_allume_rien(self, monkeypatch, brut):
        from app.config import settings

        monkeypatch.setattr(settings, "capacites_surcharge", brut)
        assert capacites._lire_depuis_le_menu() == SANS_RIEN


def test_api_config_porte_les_quatre_drapeaux(client, capacites):
    capacites(assistants=True, entraide=False)
    c = client.get("/api/config").json()
    assert c["assistants"] is True and c["entraide"] is False and "demandes" in c and "signalements" in c
