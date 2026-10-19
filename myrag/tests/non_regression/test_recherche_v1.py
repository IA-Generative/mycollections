"""Le contrat de recherche v1 figé : /api/v1/search et /scopes, corps complets.

Le lot A ajoute `assistant=` et une clé `plan` ; sans `assistant`, la réponse doit rester
celle-ci, clé par clé (contrat de recherche MirAI, lu par Mon portail). Les noms de
collections et les signatures des liens, variables, sont remplacés avant comparaison."""

from __future__ import annotations

import json
import re

from tests.non_regression._outils import figer
from tests.unit.test_recherche import ALICE, _doc, jeu, moteur, noms, reglages  # noqa: F401 — fixtures et jeu partagés


def _documents(jeu):
    return [
        _doc(
            jeu["partagee"],
            "methodes-2024",
            101,
            "# Méthodes\n\nLe budget de l'équipe est voté en janvier.",
            title="Méthodes 2024",
            created_at="2024-01-15T09:00:00+00:00",
            relevance_score=0.91,
        ),
        _doc(
            jeu["partagee"],
            "methodes-2024",
            102,
            "Le budget se révise en juin, après le bilan.",
            title="Méthodes 2024",
            created_at="2024-01-15T09:00:00+00:00",
            relevance_score=0.8,
        ),
        _doc(jeu["mienne"], "notes-budget", 201, "Notes : budget prévisionnel, puis budget réalisé.", relevance_score=0.75, page=2),
        _doc(jeu["ouverte"], "texte-public", 301, "Un texte ouvert qui parle de budget.", relevance_score=0.5),
        _doc(jeu["secrete"], "secret", 401, "Le budget secret de Bob.", relevance_score=0.99),  # hors droit : jamais rendu
    ]


def _normaliser(corps, jeu):
    texte = json.dumps(corps, ensure_ascii=False)
    for cle, nom in jeu.items():
        texte = texte.replace(nom, "{" + cle + "}")
    texte = re.sub(r"\?exp=\d+&sig=[^\"&]+", "?<signe>", texte)
    return json.loads(texte)


def test_search_sans_scope(client, en_tant_que, jeu, moteur):
    en_tant_que(ALICE)
    moteur.return_value = {"documents": _documents(jeu)}
    r = client.get("/api/v1/search", params={"q": "budget"})
    assert r.status_code == 200, r.text
    figer("recherche_v1/search_sans_scope", _normaliser(r.json(), jeu))


def test_search_avec_scope_et_limite(client, en_tant_que, jeu, moteur):
    en_tant_que(ALICE)
    moteur.return_value = {"documents": _documents(jeu)}
    r = client.get("/api/v1/search", params={"q": "budget", "scope": f"{jeu['partagee']},{jeu['secrete']}", "limit": "1"})
    assert r.status_code == 200, r.text
    figer("recherche_v1/search_avec_scope", _normaliser(r.json(), jeu))


def test_scopes(client, en_tant_que, jeu, moteur):
    en_tant_que(ALICE)
    r = client.get("/api/v1/search/scopes")
    assert r.status_code == 200
    corps = _normaliser(r.json(), jeu)
    # D'autres collections lisibles peuvent subsister d'autres modules : on ne fige que le jeu.
    corps["scopes"] = [s for s in corps["scopes"] if s["id"].startswith("{")]
    figer("recherche_v1/scopes", corps)


def test_reponse_vide_et_en_tetes(client, en_tant_que, jeu, moteur):
    en_tant_que(ALICE)
    moteur.return_value = {"documents": []}
    r = client.get("/api/v1/search", params={"q": "budget"})
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {"source": "mycollections", "query": "budget", "total": 0, "truncated": False, "total_is_lower_bound": False, "results": []}
