"""Règle 2 — un chantier ne démarre qu'à N soutiens ET un garant ; le seuil est
central, figé sur la demande, et le passage d'état est calculé côté serveur."""

from app.services.etats import demande_atteint_le_chantier
from tests.conftest import SUPERADMIN, personne
from tests.unit.test_regle1_usage_frequence import DEMANDE


def _deposer(client, en_tant_que, **extra):
    en_tant_que(personne("auteur"))
    r = client.post("/api/demandes", json={**DEMANDE, **extra})
    assert r.status_code == 201, r.text
    return r.json()["demande"]["id"]


def _soutenir(client, en_tant_que, ident, qui, role="soutien"):
    en_tant_que(qui)
    r = client.post(f"/api/demandes/{ident}/soutenir", json={"role": role})
    assert r.status_code == 200, r.text
    return r.json()["demande"]


class TestLaRegleEnPur:
    def test_le_et_n_est_pas_un_ou(self):
        assert demande_atteint_le_chantier(5, True, 5)
        assert not demande_atteint_le_chantier(5, False, 5)
        assert not demande_atteint_le_chantier(4, True, 5)
        assert demande_atteint_le_chantier(9, True, 5)


class TestSurLesRoutes:
    def test_cinq_soutiens_sans_garant_restent_ouverts(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        for n in range(5):
            d = _soutenir(client, en_tant_que, ident, personne(n))
        assert d["nb_soutiens"] == 5 and d["garant"] is False and d["etat"] == "ouverte"

    def test_un_garant_et_quatre_soutiens_restent_ouverts(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        _soutenir(client, en_tant_que, ident, personne("g"), role="garant")
        for n in range(3):
            d = _soutenir(client, en_tant_que, ident, personne(n))
        assert d["nb_soutiens"] == 4 and d["garant"] is True and d["etat"] == "ouverte"

    def test_seuil_et_garant_font_un_chantier_et_un_evenement(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        for n in range(4):
            _soutenir(client, en_tant_que, ident, personne(n))
        d = _soutenir(client, en_tant_que, ident, personne("g"), role="garant")
        assert d["etat"] == "chantier" and d["nb_soutiens"] == 5
        types = [e["type"] for e in client.get(f"/api/demandes/{ident}/journal").json()["evenements"]]
        assert "seuil.atteint" in types

    def test_le_meme_soutien_ne_compte_qu_une_fois(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        for _ in range(6):
            d = _soutenir(client, en_tant_que, ident, personne(1))
        assert d["nb_soutiens"] == 1

    def test_le_seuil_est_fige_a_la_creation(self, client, en_tant_que, capacites):
        capacites(seuil_chantier=5)
        ident = _deposer(client, en_tant_que)
        capacites(seuil_chantier=3)
        for n in range(3):
            _soutenir(client, en_tant_que, ident, personne(n))
        d = _soutenir(client, en_tant_que, ident, personne("g"), role="garant")
        assert d["seuil"] == 5 and d["etat"] == "ouverte", "3 soutiens ne suffisent pas : le seuil figé est 5"
        assert client.get("/api/demandes").json()["seuil_chantier"] == 3, "l'écran, lui, affiche le seuil courant"

    def test_l_etat_envoye_par_le_client_est_refuse(self, client, en_tant_que):
        en_tant_que(personne(1))
        assert client.post("/api/demandes", json={**DEMANDE, "etat": "chantier"}).status_code == 422
        ident = _deposer(client, en_tant_que)
        assert client.patch(f"/api/demandes/{ident}", json={"etat": "chantier"}).status_code == 422

    def test_deux_garants_est_un_conflit(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        _soutenir(client, en_tant_que, ident, personne("g1"), role="garant")
        en_tant_que(personne("g2"))
        assert client.post(f"/api/demandes/{ident}/soutenir", json={"role": "garant"}).status_code == 409

    def test_retirer_un_soutien_ne_retrograde_pas_un_chantier(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        for n in range(5):
            _soutenir(client, en_tant_que, ident, personne(n))
        assert _soutenir(client, en_tant_que, ident, personne("g"), role="garant")["etat"] == "chantier"
        en_tant_que(personne(0))
        r = client.delete(f"/api/demandes/{ident}/soutenir")
        assert r.status_code == 200 and r.json()["demande"]["etat"] == "chantier"

    def test_un_superadmin_peut_retirer_le_garant(self, client, en_tant_que):
        ident = _deposer(client, en_tant_que)
        _soutenir(client, en_tant_que, ident, personne("g"), role="garant")
        en_tant_que(SUPERADMIN)
        r = client.delete(f"/api/demandes/{ident}/garant")
        assert r.status_code == 200 and r.json()["demande"]["garant"] is False
