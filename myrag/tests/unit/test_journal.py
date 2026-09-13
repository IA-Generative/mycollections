"""Le fil d'avancement — chaque geste laisse une ligne ; un chantier muet trente
jours est en sommeil, visible de tous, et jamais stocké."""

from datetime import datetime, timedelta

import pytest

from app.services.etats import en_sommeil
from tests.conftest import personne
from tests.unit.test_regle1_usage_frequence import DEMANDE


class TestLeSommeilEnPur:
    def test_trente_et_un_jours(self):
        maintenant = datetime(2026, 9, 13)
        assert en_sommeil("chantier", maintenant - timedelta(days=31), maintenant)
        assert not en_sommeil("chantier", maintenant - timedelta(days=29), maintenant)

    def test_jamais_sur_une_demande_ouverte(self):
        maintenant = datetime(2026, 9, 13)
        assert not en_sommeil("ouverte", maintenant - timedelta(days=400), maintenant)
        assert en_sommeil("chantier", None, maintenant)


def test_chaque_geste_ecrit_un_evenement(client, en_tant_que):
    en_tant_que(personne("a"))
    ident = client.post("/api/demandes", json=DEMANDE).json()["demande"]["id"]
    en_tant_que(personne("b"))
    client.post(f"/api/demandes/{ident}/soutenir", json={"role": "relecteur", "temps_declare_min": 60})
    client.delete(f"/api/demandes/{ident}/soutenir")
    en_tant_que(personne("a"))
    client.patch(f"/api/demandes/{ident}", json={"titre": "Répertoire des élus"})
    types = [e["type"] for e in client.get(f"/api/demandes/{ident}/journal").json()["evenements"]]
    assert types == ["demande.modifiee", "soutien.retire", "soutien.ajoute", "demande.creee"]
    dernier = client.get(f"/api/demandes/{ident}/journal").json()["evenements"][2]
    assert dernier["par"] == "personne" and dernier["detail"] == {"role": "relecteur", "temps_declare_min": 60, "nb_soutiens": 1}


def test_le_journal_ne_nomme_personne(client, en_tant_que):
    en_tant_que(personne("a"))
    ident = client.post("/api/demandes", json=DEMANDE).json()["demande"]["id"]
    texte = client.get(f"/api/demandes/{ident}/journal").text
    assert "personne-a" not in texte and "auteur_hash" not in texte


def test_le_sommeil_se_lit_sur_la_demande(client, en_tant_que):
    import os
    import sqlite3
    en_tant_que(personne("a"))
    ident = client.post("/api/demandes", json=DEMANDE).json()["demande"]["id"]
    for n in range(5):
        en_tant_que(personne(n))
        client.post(f"/api/demandes/{ident}/soutenir", json={"role": "soutien"})
    en_tant_que(personne("g"))
    assert client.post(f"/api/demandes/{ident}/soutenir", json={"role": "garant"}).json()["demande"]["etat"] == "chantier"
    assert client.get(f"/api/demandes/{ident}").json()["demande"]["sommeil"] is False
    # On vieillit tous ses événements de 31 jours, directement en base.
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.execute("UPDATE evenement SET cree_le = datetime('now', '-31 days') WHERE objet_id = ?", (ident,))
    con.commit(); con.close()
    assert client.get(f"/api/demandes/{ident}").json()["demande"]["sommeil"] is True
    liste = {d["id"]: d for d in client.get("/api/demandes").json()["demandes"]}
    assert liste[ident]["sommeil"] is True


def test_la_pagination_du_journal(client, en_tant_que):
    en_tant_que(personne("a"))
    ident = client.post("/api/demandes", json=DEMANDE).json()["demande"]["id"]
    for n in range(4):
        en_tant_que(personne(n))
        client.post(f"/api/demandes/{ident}/soutenir", json={"role": "soutien"})
    page = client.get(f"/api/demandes/{ident}/journal?limite=2").json()
    assert len(page["evenements"]) == 2 and page["suivant"]
    suite = client.get(f"/api/demandes/{ident}/journal?limite=2&avant={page['suivant']}").json()
    assert len(suite["evenements"]) == 2
    assert {e["id"] for e in page["evenements"]}.isdisjoint({e["id"] for e in suite["evenements"]})


def test_l_abonnement_suit_la_creation_et_le_soutien(client, en_tant_que):
    en_tant_que(personne("a"))
    r = client.post("/api/demandes", json=DEMANDE).json()["demande"]
    assert r["abonne"] is True
    en_tant_que(personne("b"))
    assert client.get(f"/api/demandes/{r['id']}").json()["demande"]["abonne"] is False
    assert client.post(f"/api/demandes/{r['id']}/soutenir", json={"role": "soutien"}).json()["demande"]["abonne"] is True
    assert client.delete(f"/api/demandes/{r['id']}/abonner").json()["abonne"] is False


def test_un_evenement_a_un_auteur_ou_un_robot(client):
    from app.services.journal import ecrire
    with pytest.raises(ValueError):
        ecrire(None, "demande", "x", "demande.creee")
    with pytest.raises(ValueError):
        ecrire(None, "demande", "x", "demande.creee", auteur_hash="h", robot="r")
