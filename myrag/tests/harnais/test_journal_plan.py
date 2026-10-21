"""Le journal d'un plan : aucune colonne de contenu, et aucun texte de la question ni des
passages ne se retrouve en base ni dans les journaux."""

from __future__ import annotations

import logging
import os
import sqlite3

from app.harnais.contrat import JournalEtape, JournalPlan
from app.models.db import PlanJournal
from tests.harnais.conftest import IDENTITES

TEMOIN = "QUETZAL-9031"

#: Les seules colonnes de `plans_journal` : des identifiants, des compteurs, des durées, des drapeaux.
COLONNES_ATTENDUES = {
    "id", "assistant_id", "version", "empreinte", "canal", "planificateur", "consigne", "score_consigne",
    "reponse_fiable", "a_valider", "valide", "sources_ignorees", "nb_etapes", "nb_passages", "etapes_json",
    "duree_ms", "auteur_hash", "robot", "cree_le",
}  # fmt: skip


def test_aucune_colonne_de_contenu():
    colonnes = {c.name for c in PlanJournal.__table__.columns}
    assert colonnes == COLONNES_ATTENDUES
    for interdit in ("question", "query", "texte", "passage", "passages", "reponse", "contenu", "extrait", "snippet"):
        assert interdit not in colonnes


def test_le_modele_du_journal_n_a_aucun_champ_de_texte_libre():
    champs = JournalPlan.model_fields
    assert not {"question", "texte", "reponse", "passages", "query"} & set(champs)
    assert set(JournalEtape.model_fields) <= {"n", "source", "poids", "attend", "duree_ms", "passages", "erreur"}


def _lignes() -> list[tuple]:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return con.execute("SELECT * FROM plans_journal").fetchall()
    finally:
        con.close()


def test_le_temoin_de_la_question_n_apparait_ni_en_base_ni_dans_les_journaux(client, en_tant_que, jeu, assistant_publie, theatre_branche, caplog):
    caplog.set_level(logging.DEBUG)
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": f"budget {TEMOIN}", "assistant": assistant_publie})
    assert r.status_code == 200, r.text
    assert TEMOIN in r.text  # la réponse à la personne reprend sa question : c'est le contrat…
    lignes = [ligne for ligne in _lignes() if ligne[1] == assistant_publie]
    assert len(lignes) == 1  # …mais le journal en écrit une ligne
    assert TEMOIN not in " ".join(str(v) for ligne in lignes for v in ligne)
    # Les journaux de l'application et de la base (SQL compris, en DEBUG) ; pas ceux du client de test,
    # qui écrit l'adresse qu'il appelle.
    serveur = [r.getMessage() for r in caplog.records if not r.name.startswith("httpx")]
    assert serveur and TEMOIN not in " ".join(serveur)


def test_la_ligne_porte_les_compteurs_et_l_auteur_condense(client, en_tant_que, jeu, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.row_factory = sqlite3.Row
    try:
        ligne = con.execute("SELECT * FROM plans_journal WHERE assistant_id = ?", (assistant_publie,)).fetchone()
    finally:
        con.close()
    assert ligne["canal"] == "portail" and ligne["planificateur"] == "toutes_les_sources"
    assert ligne["nb_etapes"] == 2 and ligne["nb_passages"] == 4  # mienne + partagee, deux passages chacune
    assert ligne["sources_ignorees"] == 1  # `secrete` : un compte, jamais un nom
    assert ligne["robot"] is None and len(ligne["auteur_hash"]) == 64 and "alice" not in ligne["auteur_hash"]
    assert len(ligne["empreinte"]) == 64 and ligne["version"] == 1
    assert jeu["secrete"] not in ligne["etapes_json"]
