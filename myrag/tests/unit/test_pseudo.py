"""Le condensé des identités : stable, salé, jamais le sub en clair."""

import os
import sqlite3

import pytest

from app.services.pseudo import SelAbsent, condenser
from tests.conftest import personne
from tests.unit.test_regle1_usage_frequence import DEMANDE


def test_le_condense_est_stable_et_depend_du_sel():
    assert condenser("abc", "sel1") == condenser("abc", "sel1")
    assert condenser("abc", "sel1") != condenser("abc", "sel2")
    assert condenser("abc", "sel1") != condenser("abd", "sel1")
    assert len(condenser("abc", "sel1")) == 64


def test_sans_sel_on_refuse():
    with pytest.raises(SelAbsent):
        condenser("abc", "")


def test_sans_sel_les_routes_repondent_503(client, en_tant_que, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "myrag_pseudo_sel", "")
    en_tant_que(personne(1))
    assert client.post("/api/demandes", json=DEMANDE).status_code == 503


def test_aucun_sub_en_clair_apres_un_parcours(client, en_tant_que, creer_collection, nom):
    qui = personne("clair")
    en_tant_que(qui)
    ident = client.post("/api/demandes", json=DEMANDE).json()["demande"]["id"]
    client.post(f"/api/demandes/{ident}/soutenir", json={"role": "garant"})
    creer_collection(nom, qui)
    client.post(f"/api/collections/{nom}/propositions", json={"cible_type": "fichier", "apres": "v2", "justification": "j"})
    client.post(f"/api/collections/{nom}/signalements", json={"motif": "erreur", "texte": "t"})
    client.put(f"/api/collections/{nom}/grille", json={"fraicheur": "x"})
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    for table in ("demande", "soutien", "abonnement", "proposition", "signalement", "grille_controle", "evenement"):
        lignes = con.execute(f"SELECT * FROM {table}").fetchall()
        assert not any("personne-clair" in str(v) for l in lignes for v in l), table
    con.close()
