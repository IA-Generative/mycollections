"""A4 : servir une réponse fiable. Une réponse de référence validée et marquée « fiable », dont la
question ressemble assez à celle posée, est rendue telle quelle, sans aucun appel à la recherche."""

from __future__ import annotations

import os
import sqlite3

import pytest

from app.harnais.apparieur import ApparieurSacDeMots
from app.harnais.contrat import Plan, Resultat
from app.harnais.fiables import Candidat, choisir
from tests.conftest import SUPERADMIN
from tests.harnais.conftest import IDENTITES, fiche_d_essai

QUESTION = "Quel est le délai de remboursement des frais de mission ?"
REPONSE = "Les frais de mission sont remboursés sous trente jours."


def _url(ident: str, suite: str = "executer") -> str:
    return f"/api/v1/assistants/{ident}/{suite}"


def _base():
    return sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])


def _servie(ident: str) -> tuple[int, str | None]:
    con = _base()
    try:
        return con.execute("SELECT servie_fois, servie_le FROM paire_qa WHERE id = ?", (ident,)).fetchone()
    finally:
        con.close()


def _semer(
    client, en_tant_que, collection: str, question: str = QUESTION, reponse: str = REPONSE, *, fiable: bool = True, relecture: str = "valide", hors_sujet: bool = False
) -> str:
    """Une question de référence dans le jeu de `collection`, par les routes réelles."""
    en_tant_que(SUPERADMIN)
    r = client.post(f"/api/collections/{collection}/qualite/questions", json={"question": question, "reponse": reponse, "relecture": relecture, "hors_sujet": hors_sujet})
    assert r.status_code == 201, r.text
    ident = r.json()["question"]["id"]
    if fiable:
        p = client.patch(f"/api/collections/{collection}/qualite/questions/{ident}", json={"fiable": True})
        assert p.status_code == 200, p.text
    return ident


def _publier(client, en_tant_que, jeu, ident_assistant, **modifs) -> str:
    en_tant_que(SUPERADMIN)
    fiche = fiche_d_essai(jeu, ident_assistant, **modifs)
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche.model_dump(mode="json")).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    return ident_assistant


# ─── Le module pur ────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_choisir_la_plus_proche_au_dessus_du_seuil():
    candidats = [Candidat("a", "Comment poser un congé ?", "R-a", "s1"), Candidat("b", QUESTION, REPONSE, "s2")]
    retenue = await choisir(QUESTION, candidats, ApparieurSacDeMots(), 0.9)
    assert retenue is not None and retenue.candidat.id == "b" and retenue.score == 1.0
    assert retenue.reference().id == "b"


@pytest.mark.anyio
async def test_choisir_rien_sous_le_seuil_ou_sans_candidat():
    candidats = [Candidat("a", "Comment poser un congé annuel ?", "R-a", "s1")]
    assert await choisir(QUESTION, candidats, ApparieurSacDeMots(), 0.9) is None
    assert await choisir(QUESTION, [], ApparieurSacDeMots(), 0.0) is None
    assert await choisir("   ", candidats, ApparieurSacDeMots(), 0.5) is None


# ─── Servie par le moteur ─────────────────────────────────────────────────────────


def test_au_dessus_du_seuil_la_reponse_est_servie_sans_recherche(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    q = _semer(client, en_tant_que, jeu["partagee"])
    _publier(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])
    r = client.post(_url(ident_assistant), json={"question": QUESTION})
    assert r.status_code == 200, r.text
    resultat = Resultat.model_validate(r.json())
    assert resultat.reponse == REPONSE
    assert resultat.plan.etapes == [] and resultat.passages == []
    assert resultat.plan.reponse_fiable is not None and resultat.plan.reponse_fiable.id == q and resultat.plan.reponse_fiable.score == 1.0
    assert theatre_branche.appels == []
    fois, le = _servie(q)
    assert fois == 1 and le is not None
    # Le journal : une ligne, sans texte, qui dit « réponse fiable » et aucune étape.
    con = _base()
    try:
        lignes = con.execute("SELECT reponse_fiable, nb_etapes, nb_passages FROM plans_journal WHERE assistant_id = ?", (ident_assistant,)).fetchall()
        texte = " ".join(str(c) for ligne in con.execute("SELECT * FROM plans_journal WHERE assistant_id = ?", (ident_assistant,)).fetchall() for c in ligne)
    finally:
        con.close()
    assert lignes == [(1, 0, 0)]
    assert REPONSE not in texte and "remboursement" not in texte


def test_le_plan_seul_ne_compte_pas_un_service(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    q = _semer(client, en_tant_que, jeu["partagee"])
    _publier(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])
    plan = Plan.model_validate(client.post(_url(ident_assistant, "plan"), json={"question": QUESTION}).json())
    assert plan.reponse_fiable is not None and plan.etapes == []
    assert _servie(q)[0] == 0
    # Le client renvoie ce plan à `executer` : servi une fois, comme s'il avait planifié lui-même.
    r = client.post(_url(ident_assistant), json={"question": QUESTION, "plan": plan.model_dump(mode="json")})
    assert r.status_code == 200 and r.json()["reponse"] == REPONSE
    assert _servie(q)[0] == 1 and theatre_branche.appels == []


def test_sous_le_seuil_la_recherche_est_normale(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    q = _semer(client, en_tant_que, jeu["partagee"])
    _publier(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])
    r = client.post(_url(ident_assistant), json={"question": "Comment est voté le budget de l'équipe ?"})
    assert r.status_code == 200, r.text
    resultat = Resultat.model_validate(r.json())
    assert resultat.reponse is None and resultat.plan.reponse_fiable is None
    assert resultat.plan.etapes and resultat.passages and theatre_branche.appels
    assert _servie(q)[0] == 0


def test_deux_assistants_aux_seuils_differents_deux_issues(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    q = _semer(client, en_tant_que, jeu["partagee"])
    autre = f"{ident_assistant}-b"
    try:
        _publier(client, en_tant_que, jeu, ident_assistant, seuil_fiable=0.5)
        _publier(client, en_tant_que, jeu, autre, seuil_fiable=0.99)
        en_tant_que(IDENTITES["alice"])
        proche = "Délai de remboursement des frais ?"  # ressemble, sans être identique
        souple = client.post(_url(ident_assistant), json={"question": proche}).json()
        strict = client.post(_url(autre), json={"question": proche}).json()
        assert souple["reponse"] == REPONSE and souple["plan"]["reponse_fiable"]["id"] == q
        assert souple["plan"]["reponse_fiable"]["score"] < 0.99
        assert strict["reponse"] is None and strict["plan"]["reponse_fiable"] is None and strict["plan"]["etapes"]
    finally:
        con = _base()
        for t in ("assistant_versions", "consignes", "plans_journal"):
            con.execute(f"DELETE FROM {t} WHERE assistant_id = ?", (autre,))
        con.execute("DELETE FROM evenement WHERE objet_type = 'assistant' AND objet_id = ?", (autre,))
        con.execute("DELETE FROM assistants WHERE id = ?", (autre,))
        con.commit()
        con.close()


def test_une_reponse_fiable_d_une_collection_illisible_n_est_jamais_servie(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    """`secrete` est une source de la fiche, mais Alice ne la lit pas."""
    q = _semer(client, en_tant_que, jeu["secrete"], reponse="Réponse secrète de Bob.")
    _publier(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])
    r = client.post(_url(ident_assistant), json={"question": QUESTION})
    assert r.status_code == 200, r.text
    assert "Réponse secrète" not in r.text and r.json()["reponse"] is None and r.json()["plan"]["reponse_fiable"] is None
    assert theatre_branche.appels and _servie(q)[0] == 0
    # Un plan fabriqué qui la cite est refusé, et rien n'est compté.
    faux = Plan(assistant=ident_assistant, version=1, planificateur="regles", reponse_fiable={"id": q, "score": 1.0}).model_dump(mode="json")
    refus = client.post(_url(ident_assistant), json={"question": QUESTION, "plan": faux})
    assert refus.status_code == 400 and "Réponse secrète" not in refus.text and _servie(q)[0] == 0
    # Bob, lui, la lit : elle lui est servie.
    en_tant_que(IDENTITES["bob"])
    assert client.post(_url(ident_assistant), json={"question": QUESTION}).json()["reponse"] == "Réponse secrète de Bob."


def test_une_question_non_validee_ou_hors_sujet_n_est_jamais_candidate(client, en_tant_que, jeu, ident_assistant, theatre_branche):
    # Non fiable, brute, hors sujet : aucune n'est servable, même identique à la question posée.
    _semer(client, en_tant_que, jeu["partagee"], question=QUESTION, fiable=False)
    _semer(client, en_tant_que, jeu["partagee"], question=QUESTION + " (brute)", relecture="brut", fiable=False)
    hors = _semer(client, en_tant_que, jeu["partagee"], question=QUESTION + " (hors sujet)", reponse="", hors_sujet=True, fiable=False)
    _publier(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(SUPERADMIN)
    # `fiable` exige validée et pas hors sujet : le serveur refuse de marquer la hors sujet.
    assert client.patch(f"/api/collections/{jeu['partagee']}/qualite/questions/{hors}", json={"fiable": True}).status_code in (409, 422)
    en_tant_que(IDENTITES["alice"])
    for question in (QUESTION, QUESTION + " (brute)", QUESTION + " (hors sujet)"):
        r = client.post(_url(ident_assistant), json={"question": question}).json()
        assert r["reponse"] is None and r["plan"]["reponse_fiable"] is None
    # Une question redevenue non validée après avoir été fiable cesse d'être servie.
    q = _semer(client, en_tant_que, jeu["partagee"], question="Combien de jours de télétravail par semaine ?", reponse="Deux jours.")
    en_tant_que(SUPERADMIN)
    assert client.patch(f"/api/collections/{jeu['partagee']}/qualite/questions/{q}", json={"relecture": "rejete"}).status_code == 200
    en_tant_que(IDENTITES["alice"])
    assert client.post(_url(ident_assistant), json={"question": "Combien de jours de télétravail par semaine ?"}).json()["reponse"] is None
