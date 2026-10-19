"""La mesure de qualité de bout en bout (réponses et juge scriptés), et la synthèse."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mesure import execution, juge
from app.services.reponse import Reponse
from tests.conftest import personne

URL = "/api/collections/{}/qualite"

REPONSES = {
    "Quel délai ?": Reponse("Deux mois.", sources=[{"filename": "a.md"}], source_names=["a.md"]),
    "Quelles pièces ?": Reponse("Un passeport.", sources=[{"filename": "b.md"}], source_names=["b.md"]),
    "Âge du capitaine ?": Reponse("Je ne dispose pas d'information sur ce sujet.", sources=[{"filename": "a.md"}], source_names=["a.md"]),
    "Hors champ décrit ?": Reponse("La collection contient trois notes.", sources=[{"filename": "c.md"}], source_names=["c.md"], repli="fichiers"),
    "Introuvable ?": Reponse("Je n'ai rien.", sources=[], source_names=[]),
}
JUGEMENTS = {"Deux mois.": juge.Jugement("conforme", "Mêmes faits."), "Un passeport.": juge.Jugement("non_conforme", "Il manque le justificatif de domicile.")}


@pytest.fixture(autouse=True)
def rapide(monkeypatch):
    monkeypatch.setattr(execution, "INTERVALLE_SUIVI_S", 0.05)


def _jeu(client, nom):
    for q, r, hs in [
        ("Quel délai ?", "Deux mois.", False),
        ("Quelles pièces ?", "Passeport et justificatif de domicile.", False),
        ("Âge du capitaine ?", "", True),
        ("Hors champ décrit ?", "", True),
        ("Introuvable ?", "Quelque chose.", False),
    ]:
        assert client.post(URL.format(nom) + "/questions", json={"question": q, "reponse": r, "hors_sujet": hs, "relecture": "valide"}).status_code == 201
    client.post(URL.format(nom) + "/questions", json={"question": "Pas encore relue ?", "reponse": "x"})  # brut : pas mesurée


async def _repondre(collection, question, *, client):
    return REPONSES[question]


async def _juger(question, reference, obtenue, *, compteurs, debit=None):
    compteurs.appels_llm += 1
    return JUGEMENTS[obtenue]


def _mesurer(client, nom, juger=_juger):
    sain = MagicMock()
    sain.return_value.health_check = AsyncMock(return_value=True)
    with patch.object(execution, "repondre", new=_repondre), patch.object(execution.juge_mod, "juger", new=juger), patch.object(execution, "OpenRAGClient", new=sain):
        r = client.post(URL.format(nom) + "/mesures", json={})
        assert r.status_code == 202, r.text
        mid = r.json()["mesure"]["id"]
        for _ in range(200):
            m = client.get(URL.format(nom) + f"/mesures/{mid}").json()["mesure"]
            if not m["actif"]:
                return m
            time.sleep(0.02)
    raise AssertionError("la mesure ne s'est pas terminée")


def test_mesure_complete_verdicts_score_et_dernier_verdict(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    _jeu(client, nom)
    m = _mesurer(client, nom)
    assert m["etat"] == "termine" and m["nb_questions"] == 5 and m["nb_traitees"] == 5
    assert m["verdicts"] == {"conformes": 1, "partielles": 0, "non_conformes": 1, "refus_ok": 1, "refus_ko": 1, "sans_source": 1, "erreurs": 0}
    assert m["score"] == 40.0 and m["methode"] == "judge" and m["compteurs"]["appels_chat"] == 5
    res = client.get(URL.format(nom) + f"/mesures/{m['id']}/resultats").json()
    assert res["total"] == 5
    pieces = next(r for r in res["resultats"] if r["question"] == "Quelles pièces ?")
    assert pieces["verdict"] == "non_conforme" and "justificatif" in pieces["justification"] and pieces["reponse_obtenue"] == "Un passeport."
    nc = client.get(URL.format(nom) + f"/mesures/{m['id']}/resultats", params={"verdict": "non_conforme"}).json()
    assert nc["total"] == 1
    jeu = {q["question"]: q for q in client.get(URL.format(nom) + "/questions", params={"par_page": 50}).json()["questions"]}
    assert jeu["Quelles pièces ?"]["dernier_verdict"] == "non_conforme" and jeu["Pas encore relue ?"]["dernier_verdict"] is None
    synth = client.get(URL.format(nom)).json()
    assert synth["derniere_terminee"]["score"] == 40.0 and synth["appreciation"] == "à améliorer"
    assert [t["score"] for t in synth["tendance"]] == [40.0]
    codes = {a["code"] for a in synth["actions"]}
    assert {"corriger_echecs", "regle_de_garde", "valider_questions"} <= codes


def test_juge_injoignable_bascule_sur_la_similarite(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    _jeu(client, nom)

    async def en_panne(*a, **k):
        raise juge.JugeIndisponible("ConnectError")

    m = _mesurer(client, nom, juger=en_panne)
    assert m["etat"] == "termine" and m["methode"] == "similarite"
    res = client.get(URL.format(nom) + f"/mesures/{m['id']}/resultats", params={"verdict": "conforme"}).json()
    assert res["total"] == 1 and res["resultats"][0]["methode"] == "similarite"


def test_garde_fous(client, en_tant_que, creer_collection, nom, monkeypatch):
    from app.config import settings

    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    assert client.post(URL.format(nom) + "/mesures", json={}).status_code == 403
    assert client.get(URL.format(nom)).status_code == 403
    en_tant_que(personne("createur"))
    r = client.post(URL.format(nom) + "/mesures", json={})
    assert r.status_code == 409 and "validez" in r.json()["detail"]
    _jeu(client, nom)
    monkeypatch.setattr(settings, "mesure_questions_max", 2)
    assert client.post(URL.format(nom) + "/mesures", json={}).status_code == 413


def test_actions_suggerees():
    from app.models.qualite import ComptesQuestions, MesureFiche
    from app.services.qualite import actions_suggerees

    def comptes(**surcharge) -> ComptesQuestions:
        base = ComptesQuestions(total=0, par_origine={}, par_relecture={}, par_verdict={}, fiables=0, hors_sujet=0)
        return base.model_copy(update=surcharge) if surcharge else base

    def mesure(**surcharge) -> MesureFiche:
        base = MesureFiche(
            id="m",
            collection="c",
            etat="termine",
            phase="fini",
            actif=False,
            methode="judge",
            modele="",
            filtre={},
            nb_questions=10,
            nb_traitees=10,
            verdicts={},
            score=None,
            compteurs={},
            duree_s=None,
            erreur=None,
            cree_le=None,
            demarre_le=None,
            termine_le=None,
        )
        return base.model_copy(update=surcharge) if surcharge else base

    assert actions_suggerees(comptes(), None, {})[0]["code"] == "constituer_jeu"
    codes = [a["code"] for a in actions_suggerees(comptes(total=3, par_relecture={"brut": 3}), None, {"pending_review": 2})]
    assert codes == ["valider_questions", "traiter_avis"]
    derniere = mesure(
        cree_le="2026-10-15T10:00:00",
        verdicts={"non_conformes": 1, "partielles": 1, "sans_source": 3, "refus_ko": 0},
    )
    codes = [a["code"] for a in actions_suggerees(comptes(total=10, par_relecture={"valide": 10}), derniere, {})]
    assert codes == ["corriger_echecs", "redecouper"]


def test_volet_dernier_resultat_et_retester(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    _jeu(client, nom)
    _mesurer(client, nom)
    qid = next(q["id"] for q in client.get(URL.format(nom) + "/questions", params={"par_page": 50}).json()["questions"] if q["question"] == "Quelles pièces ?")
    d = client.get(URL.format(nom) + f"/questions/{qid}").json()
    assert d["dernier_resultat"]["verdict"] == "non_conforme" and d["dernier_resultat"]["reponse_obtenue"] == "Un passeport."
    with patch.object(execution, "repondre", new=_repondre), patch.object(execution.juge_mod, "juger", new=_juger):
        r = client.post(URL.format(nom) + f"/questions/{qid}/tester").json()
    assert r["verdict"] == "non_conforme" and r["reponse_obtenue"] == "Un passeport." and r["sources"] == [{"fichier": "b.md"}]
