"""API de génération : droits, disponibilité, personas, runs en tâche de fond, relecture, exports.

Le moteur ragas est remplacé par une fonction simulée : ces tests tournent sans ragas ni passerelle.
"""

from __future__ import annotations

import csv
import io
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.generation import execution
from app.generation.morceaux import Morceau
from app.generation.resultats import PaireGeneree, ResultatGeneration
from tests.conftest import SUPERADMIN, personne

URL = "/api/collections/{}/generation"


@pytest.fixture(autouse=True)
def configuree(monkeypatch):
    monkeypatch.setattr(settings, "generation_llm_url", "https://passerelle.fake-domain.name/v1")
    monkeypatch.setattr(settings, "generation_llm_cle", "cle-de-test")
    monkeypatch.setattr(settings, "generation_llm_modele", "chat")
    monkeypatch.setattr("app.generation.disponible", lambda: True)
    monkeypatch.setattr(execution, "INTERVALLE_SUIVI_S", 0.05)


@pytest.fixture
def collection(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    return nom


def _morceaux(n=3):
    return [Morceau(f"c{i}", f"f{i}", "x", f"doc-{i}.md", None, f"Passage numéro {i} assez long pour servir.") for i in range(n)]


def _paires(n=3):
    return [
        PaireGeneree(
            question=f"=Question {i} ?",
            reponse=f"Réponse {i}",
            persona_nom="Agent" if i % 2 else "Technicien",
            synthetiseur="paire_simple_entites",
            style="Perfect grammar",
            longueur="short",
            contextes=[{"chunk_id": f"c{i}", "file_id": f"f{i}", "partition": "x", "fichier": f"doc-{i}.md", "page": None, "texte": f"Passage numéro {i}"}],
        )
        for i in range(n)
    ]


def _faux_moteur(resultat):
    def generer(morceaux, personas, taille, distribution, compteurs):
        compteurs.poser_phase("generation")
        compteurs.observer("x", None, 0.1)
        return resultat

    return generer


def _lancer(client, nom, personas, resultat=None, morceaux=None, **corps):
    resultat = resultat or ResultatGeneration(etat="termine", paires=_paires(), morceaux_envoyes=3, noeuds_avec_proprietes=3)
    with (
        patch("app.routers.generation.corpus.fichiers_de", new=AsyncMock(return_value=[{"file_id": "f0"}])),
        patch("app.generation.execution.lire_echantillon", new=AsyncMock(return_value=(morceaux if morceaux is not None else _morceaux(), 3))),
        patch("app.generation.execution.generer_dans_le_fil", new=_faux_moteur(resultat)),
    ):
        r = client.post(URL.format(nom) + "/runs", json={"personas": personas, "taille": 3, **corps})
        assert r.status_code == 202, r.text
        run_id = r.json()["run"]["id"]
        for _ in range(200):
            run = client.get(URL.format(nom) + f"/runs/{run_id}").json()["run"]
            if not run["actif"]:
                return run
            time.sleep(0.02)
    raise AssertionError("le run ne s'est pas terminé")


def _persona(client, nom, n="Agent", d="Agent de préfecture au guichet étrangers."):
    r = client.post(URL.format(nom) + "/personas", json={"nom": n, "description_role": d})
    assert r.status_code == 201, r.text
    return r.json()["persona"]["id"]


def test_503_qui_dit_ce_qui_manque(client, collection, monkeypatch):
    monkeypatch.setattr(settings, "generation_llm_cle", "")
    r = client.get(URL.format(collection))
    assert r.status_code == 503 and "MYCOLLECTIONS_GENERATION_LLM_CLE" in r.json()["detail"]
    monkeypatch.setattr("app.generation.disponible", lambda: False)
    assert "extra « generation »" in client.get(URL.format(collection)).json()["detail"]
    assert client.get("/api/config").json()["generation"] is False


def test_reserve_a_qui_gere(client, en_tant_que, collection):
    en_tant_que(personne("lecteur"))
    assert client.get(URL.format(collection)).status_code == 403
    assert client.post(URL.format(collection) + "/personas", json={"nom": "a", "description_role": "b"}).status_code == 403
    en_tant_que(personne("etranger").__class__(sub="dehors", username="d", groups=["/g/autre"]))
    assert client.get(URL.format(collection)).status_code == 404
    en_tant_que(SUPERADMIN)
    assert client.get(URL.format(collection)).status_code == 200


def test_personas_crud(client, collection):
    pid = _persona(client, collection)
    assert client.post(URL.format(collection) + "/personas", json={"nom": "Agent", "description_role": "x"}).status_code == 409
    assert client.post(URL.format(collection) + "/personas", json={"nom": "B", "description_role": "x", "role": 1}).status_code == 422
    r = client.patch(URL.format(collection) + f"/personas/{pid}", json={"description_role": "Autre contexte"})
    assert r.json()["persona"]["description_role"] == "Autre contexte"
    assert client.patch(URL.format(collection) + f"/personas/{pid}", json={}).status_code == 422
    assert [p["nom"] for p in client.get(URL.format(collection) + "/personas").json()["personas"]] == ["Agent"]
    assert client.delete(URL.format(collection) + f"/personas/{pid}").status_code == 200
    assert client.delete(URL.format(collection) + f"/personas/{pid}").status_code == 404


def test_run_complet_paires_compteurs_journal(client, collection):
    ids = [_persona(client, collection, "Agent"), _persona(client, collection, "Technicien", "Support informatique.")]
    run = _lancer(client, collection, ids)
    assert run["etat"] == "termine" and run["phase"] == "fini", run
    assert run["paires_obtenues"] == 3 and run["morceaux_envoyes"] == 3 and run["fichiers_collection"] == 3
    assert run["compteurs"]["appels_llm"] == 1 and run["duree_s"] is not None
    assert [p["nom"] for p in run["personas"]] == ["Agent", "Technicien"]
    page = client.get(URL.format(collection) + f"/runs/{run['id']}/paires").json()
    assert page["total"] == 3 and page["paires"][0]["contextes"][0]["chunk_id"] == "c0"
    assert page["paires"][0]["relecture"] == "brut"
    filtre = client.get(URL.format(collection) + f"/runs/{run['id']}/paires", params={"persona": "Agent"}).json()
    assert filtre["total"] == 1
    types = [e["type"] for e in client.get(f"/api/collections/{collection}/journal").json()["evenements"]]
    assert "generation.lancee" in types and "generation.terminee" in types


def test_relecture(client, collection):
    run = _lancer(client, collection, [_persona(client, collection)])
    pid = client.get(URL.format(collection) + f"/runs/{run['id']}/paires").json()["paires"][1]["id"]
    r = client.patch(URL.format(collection) + f"/paires/{pid}", json={"relecture": "rejete", "commentaire": "Hors sujet"})
    assert r.json()["paire"]["relecture"] == "rejete" and r.json()["paire"]["relu_le"]
    assert client.patch(URL.format(collection) + f"/paires/{pid}", json={"relecture": "bof"}).status_code == 422
    rej = client.get(URL.format(collection) + f"/runs/{run['id']}/paires", params={"relecture": "rejete"}).json()
    assert rej["total"] == 1 and rej["paires"][0]["commentaire"] == "Hors sujet"
    r = client.patch(URL.format(collection) + f"/paires/{pid}", json={"relecture": "brut"})
    assert r.json()["paire"]["relu_le"] is None


def test_exports(client, collection):
    run = _lancer(client, collection, [_persona(client, collection)])
    r = client.get(URL.format(collection) + f"/runs/{run['id']}/export", params={"format": "json"})
    assert 'attachment; filename="' in r.headers["content-disposition"]
    d = r.json()
    assert d["metadata"]["total_samples"] == 3
    s = d["samples"][0]
    assert set(s) == {"question", "answer", "context", "persona_name", "query_style", "metadata"}
    assert s["metadata"]["chunk_ids"] == ["c0"]
    r = client.get(URL.format(collection) + f"/runs/{run['id']}/export", params={"format": "csv"})
    assert r.text.startswith("﻿")
    lignes = list(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    assert lignes[0][:3] == ["id", "persona", "question"]
    assert lignes[1][2].startswith("'="), "une cellule qui commence par = est neutralisée"


def test_garde_conflits_et_erreurs(client, collection):
    pid = _persona(client, collection)
    autre = "00000000-0000-0000-0000-000000000000"
    with patch("app.routers.generation.corpus.fichiers_de", new=AsyncMock(return_value=[{"file_id": "f"}])):
        assert client.post(URL.format(collection) + "/runs", json={"personas": [autre]}).status_code == 404
        assert client.post(URL.format(collection) + "/runs", json={"personas": [pid, pid]}).status_code == 422
        assert client.post(URL.format(collection) + "/runs", json={"personas": [pid], "taille": 500}).status_code == 422
        assert client.post(URL.format(collection) + "/runs", json={"personas": [pid], "distribution": {"x": 1}}).status_code == 422
    with patch("app.routers.generation.corpus.fichiers_de", new=AsyncMock(return_value=[])):
        assert client.post(URL.format(collection) + "/runs", json={"personas": [pid]}).status_code == 409


def test_run_en_erreur_motive_sans_texte(client, collection):
    pid = _persona(client, collection)
    run = _lancer(client, collection, [pid], resultat=ResultatGeneration(etat="erreur", erreur="Le modèle de langage ne répond pas."))
    assert run["etat"] == "erreur" and "ne répond pas" in run["erreur"]
    run = _lancer(client, collection, [pid], morceaux=[])
    assert run["etat"] == "erreur" and "Aucun passage" in run["erreur"]


def test_second_run_refuse_pendant_le_premier(client, collection):
    import asyncio

    from app.services import generation_store as store

    pid = _persona(client, collection)
    personas = asyncio.run(store.personas_par_ids(collection, [pid]))
    asyncio.run(store.creer_run(collection, personas, 3, {"entites": 1.0}, "chat", "x"))
    with patch("app.routers.generation.corpus.fichiers_de", new=AsyncMock(return_value=[{"file_id": "f"}])):
        assert client.post(URL.format(collection) + "/runs", json={"personas": [pid]}).status_code == 409
    assert asyncio.run(store.marquer_interrompus()) >= 1
    run = client.get(URL.format(collection) + "/runs").json()["runs"][0]
    assert run["etat"] == "erreur" and "redémarrage" in run["erreur"]


def test_suppression_d_un_run(client, collection):
    run = _lancer(client, collection, [_persona(client, collection)])
    assert client.delete(URL.format(collection) + f"/runs/{run['id']}").status_code == 200
    assert client.get(URL.format(collection) + f"/runs/{run['id']}").status_code == 404


def test_une_ligne_de_bilan_par_run_sans_contenu(client, collection):
    import logging

    lignes: list[str] = []

    class Recueil(logging.Handler):
        def emit(self, record):
            lignes.append(record.getMessage())

    journal = logging.getLogger("myrag.generation")
    assert journal.handlers and journal.level == logging.INFO, "la ligne de bilan doit sortir quelque part"
    recueil = Recueil()
    journal.addHandler(recueil)
    try:
        run = _lancer(client, collection, [_persona(client, collection)])
    finally:
        journal.removeHandler(recueil)
    ligne = next(m for m in lignes if "generation run=" + run["id"] in m)
    assert f"collection={collection}" in ligne and "paires=3" in ligne and "appels_llm=1" in ligne
    assert not any("Passage numéro" in m or "Question" in m for m in lignes)
