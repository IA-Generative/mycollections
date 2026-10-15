"""Le jeu de questions de référence : droits, saisie, import, édition, règles, export, avis."""

from __future__ import annotations

import csv
import io

from tests.conftest import personne

URL = "/api/collections/{}/qualite/questions"


def _creer(client, nom, **champs):
    corps = {"question": "Quel est le délai d'instruction ?", "reponse": "Deux mois.", **champs}
    r = client.post(URL.format(nom), json=corps)
    assert r.status_code == 201, r.text
    return r.json()["question"]


def test_reserve_a_qui_gere(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    assert client.get(URL.format(nom)).status_code == 403
    assert client.post(URL.format(nom), json={"question": "Bonjour ?"}).status_code == 403
    en_tant_que(personne("x").__class__(sub="dehors", username="d", groups=["/g/autre"]))
    assert client.get(URL.format(nom)).status_code == 404


def test_saisie_lecture_et_comptes(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    q = _creer(client, nom, relecture="valide", tags=["délais"])
    assert q["origine"] == "saisie" and q["relecture"] == "valide" and q["tags"] == ["délais"] and q["run_id"] is None
    assert client.post(URL.format(nom), json={"question": "quel est le DÉLAI d'instruction"}).status_code == 409
    page = client.get(URL.format(nom)).json()
    assert page["total"] == 1 and page["comptes"]["par_origine"] == {"saisie": 1}
    assert page["comptes"]["par_verdict"] == {"jamais": 1}


def test_editer_efface_le_verdict_et_trace(client, en_tant_que, creer_collection, nom):
    import asyncio

    from app.services import questions_store as store

    creer_collection(nom)
    en_tant_que(personne("createur"))
    q = _creer(client, nom, relecture="valide")
    asyncio.run(store.noter_verdict(q["id"], "non_conforme", "m1"))
    r = client.patch(URL.format(nom) + f"/{q['id']}", json={"reponse": "Deux mois, prolongeables d'un mois."})
    q2 = r.json()["question"]
    assert q2["reponse"].startswith("Deux mois, prolongeables") and q2["dernier_verdict"] is None and q2["modifie_le"]
    # Changer seulement un tag ne touche pas au verdict.
    asyncio.run(store.noter_verdict(q["id"], "conforme", "m2"))
    assert client.patch(URL.format(nom) + f"/{q['id']}", json={"tags": ["a"]}).json()["question"]["dernier_verdict"] == "conforme"


def test_regles_de_la_reponse_fiable(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    brut = _creer(client, nom)
    assert client.patch(URL.format(nom) + f"/{brut['id']}", json={"fiable": True}).status_code == 409
    ok = client.patch(URL.format(nom) + f"/{brut['id']}", json={"relecture": "valide", "fiable": True})
    assert ok.status_code == 200 and ok.json()["question"]["fiable"] is True
    rej = client.patch(URL.format(nom) + f"/{brut['id']}", json={"relecture": "rejete"}).json()["question"]
    assert rej["fiable"] is False
    hs = _creer(client, nom, question="Quel est l'âge du capitaine ?", reponse="", hors_sujet=True, relecture="valide")
    assert client.patch(URL.format(nom) + f"/{hs['id']}", json={"fiable": True}).status_code == 409
    assert client.patch(URL.format(nom) + f"/{hs['id']}", json={"origine": "x"}).status_code == 422


def test_import_deux_formats_et_doublons(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    _creer(client, nom)
    r = client.post(
        URL.format(nom) + "/import",
        json={
            "questions": [
                {"question": "Quel est le délai d'instruction ?", "expected_answer": "doublon"},
                {"question": "Où déposer le dossier ?", "expected_answer": "Au guichet.", "must_cite": ["guichet"]},
                {"question": "Quelle est la capitale de la Mongolie ?", "expected_answer": "", "out_of_scope": True},
                {"pas": "de question"},
            ]
        },
    )
    assert r.status_code == 201 and r.json() == {"crees": 2, "doublons": 1, "ignores": 1}
    r = client.post(
        URL.format(nom) + "/import",
        json={
            "samples": [
                {"question": "Faut-il un rendez-vous ?", "answer": "Oui.", "persona_name": "Usager", "metadata": {"relecture": "brut"}},
            ]
        },
    )
    assert r.json()["crees"] == 1
    toutes = {q["question"]: q for q in client.get(URL.format(nom), params={"par_page": 50}).json()["questions"]}
    assert toutes["Où déposer le dossier ?"]["relecture"] == "valide" and toutes["Où déposer le dossier ?"]["must_cite"] == ["guichet"]
    # Hors sujet : complète sans réponse (l'attendu est un refus), donc validée.
    assert toutes["Quelle est la capitale de la Mongolie ?"]["hors_sujet"] is True and toutes["Quelle est la capitale de la Mongolie ?"]["relecture"] == "valide"
    assert toutes["Faut-il un rendez-vous ?"]["persona"] == "Usager" and toutes["Faut-il un rendez-vous ?"]["relecture"] == "brut"
    assert client.post(URL.format(nom) + "/import", json={}).status_code == 422


def test_filtres(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    _creer(client, nom, relecture="valide")
    _creer(client, nom, question="Où déposer ?", reponse="")
    assert client.get(URL.format(nom), params={"relecture": "brut"}).json()["total"] == 1
    assert client.get(URL.format(nom), params={"q": "déposer"}).json()["total"] == 1
    assert client.get(URL.format(nom), params={"verdict": "jamais"}).json()["total"] == 2


def test_export_json_et_csv(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    _creer(client, nom, question="=1+1 ?", reponse="Deux.", relecture="valide")
    r = client.get(URL.format(nom) + "/export", params={"format": "json"})
    assert r.json()["samples"][0]["metadata"]["origine"] == "saisie"
    r = client.get(URL.format(nom) + "/export", params={"format": "csv"})
    assert r.text.startswith("﻿") and "attachment" in r.headers["content-disposition"]
    lignes = list(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    assert lignes[1][1].startswith("'=")


def test_un_avis_devient_une_question(client, en_tant_que, creer_collection, nom):
    import asyncio

    from app.services import feedback_store

    creer_collection(nom)
    en_tant_que(personne("createur"))
    fb = asyncio.run(feedback_store.ingest_feedback(nom, "Puis-je travailler avec un récépissé ?", "Je ne sais pas.", -1, "faux"))
    r = client.post(URL.format(nom) + f"/depuis-avis/{fb['id']}", json={"reponse": "Oui, si le récépissé le mentionne."})
    assert r.status_code == 201
    q = r.json()["question"]
    assert q["origine"] == "avis" and q["feedback_id"] == fb["id"] and q["relecture"] == "valide"
    assert client.post(URL.format(nom) + f"/depuis-avis/{fb['id']}", json={}).status_code == 409
    assert client.post(URL.format(nom) + "/depuis-avis/999999", json={}).status_code == 404


def test_suppression_d_une_question(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    q = _creer(client, nom)
    assert client.delete(URL.format(nom) + f"/{q['id']}").status_code == 200
    assert client.get(URL.format(nom) + f"/{q['id']}").status_code == 404


def test_supprimer_un_run_garde_les_questions_validees(client, en_tant_que, creer_collection, nom):
    import asyncio

    from app.generation.resultats import PaireGeneree
    from app.services import generation_store as gs

    creer_collection(nom)
    en_tant_que(personne("createur"))
    run = asyncio.run(gs.creer_run(nom, [{"id": "p", "nom": "Agent"}], 3, {"entites": 1.0}, "chat", "x"))
    asyncio.run(gs.terminer_run(run["id"], "termine"))
    paires = [PaireGeneree(question=f"Question {i} ?", reponse="R", contextes=[], persona_nom="Agent", synthetiseur="s", style="", longueur="") for i in range(3)]
    asyncio.run(gs.enregistrer_paires(run["id"], nom, paires))
    ids = [q["id"] for q in client.get(URL.format(nom)).json()["questions"]]
    client.patch(URL.format(nom) + f"/{ids[0]}", json={"relecture": "valide"})
    asyncio.run(gs.supprimer_run(nom, run["id"]))
    reste = client.get(URL.format(nom)).json()["questions"]
    assert [q["id"] for q in reste] == [ids[0]] and reste[0]["run_id"] is None and reste[0]["origine"] == "generee"


def test_la_purge_efface_le_jeu_de_questions(client, en_tant_que, creer_collection, nom):
    import asyncio
    import os
    import sqlite3
    from unittest.mock import AsyncMock, patch

    from app.services import collection_store

    creer_collection(nom)
    en_tant_que(personne("createur"))
    _creer(client, nom)
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.execute("UPDATE collections SET archived_at = CURRENT_TIMESTAMP WHERE name = ?", (nom,))
    con.commit()
    con.close()
    with patch("app.services.openrag_client.OpenRAGClient.delete_partition", new=AsyncMock(return_value={"status": "ok"})):
        rapport = asyncio.run(collection_store.purge_collection(nom))
    assert "paire_qa" in str(rapport)
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    assert con.execute("SELECT COUNT(*) FROM paire_qa WHERE collection_name = ?", (nom,)).fetchone()[0] == 0
    con.close()
