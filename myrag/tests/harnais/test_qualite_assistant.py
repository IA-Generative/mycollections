"""La qualité d'un assistant, côté serveur : l'union en lecture des jeux de questions de ses sources
lisibles, et la synthèse par source. Aucune écriture."""

from __future__ import annotations

from tests.conftest import SUPERADMIN
from tests.harnais.conftest import IDENTITES
from tests.harnais.test_fiables import _publier, _semer

#: Une question par source, de mots bien distincts ; `partagee` en a deux (une fiable, une brute).
QUESTIONS = {
    "mienne": ("Comment poser un congé annuel ?", "Via le portail des ressources humaines."),
    "partagee": ("Quel est le délai de remboursement des frais ?", "Trente jours."),
    "secrete": ("Quelle est la clé du coffre ?", "Réponse secrète de Bob."),
}


def _monter(client, en_tant_que, jeu, ident_assistant) -> dict[str, str]:
    ids = {k: _semer(client, en_tant_que, jeu[k], *QUESTIONS[k]) for k in QUESTIONS}
    ids["brute"] = _semer(client, en_tant_que, jeu["partagee"], "Combien de jours de télétravail ?", "Deux.", fiable=False, relecture="brut")
    _publier(client, en_tant_que, jeu, ident_assistant)
    return ids


def _liste(client, ident, **params) -> dict:
    r = client.get(f"/api/assistants/{ident}/qualite/questions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_l_union_se_limite_aux_sources_lisibles(client, en_tant_que, jeu, ident_assistant):
    ids = _monter(client, en_tant_que, jeu, ident_assistant)
    attendu = {
        "alice": {ids["mienne"], ids["partagee"], ids["brute"]},
        "bob": {ids["partagee"], ids["brute"], ids["secrete"]},
        "superadmin": set(ids.values()),
    }
    for qui, voulues in attendu.items():
        en_tant_que(IDENTITES[qui])
        corps = _liste(client, ident_assistant)
        assert {q["id"] for q in corps["questions"]} == voulues, qui
        assert corps["total"] == len(voulues)
        for q in corps["questions"]:
            assert q["collection"] in jeu.values() and q["collection_titre"]
            assert {"fiable", "relecture", "servie_fois", "dernier_verdict", "peut_gerer"} <= set(q)
    # Alice ne voit ni la collection, ni la question, ni la réponse de `secrete` : nulle part dans la réponse.
    en_tant_que(IDENTITES["alice"])
    r = client.get(f"/api/assistants/{ident_assistant}/qualite/questions")
    assert jeu["secrete"] not in r.text and "Réponse secrète" not in r.text and "coffre" not in r.text
    # Qui ne lit aucune source n'a même pas l'assistant.
    en_tant_que(IDENTITES["dehors"])
    assert client.get(f"/api/assistants/{ident_assistant}/qualite/questions").status_code == 404
    assert client.get(f"/api/assistants/{ident_assistant}/qualite").status_code == 404


def test_les_filtres(client, en_tant_que, jeu, ident_assistant):
    ids = _monter(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])
    assert {q["id"] for q in _liste(client, ident_assistant, fiable="true")["questions"]} == {ids["mienne"], ids["partagee"]}
    assert {q["id"] for q in _liste(client, ident_assistant, fiable="false")["questions"]} == {ids["brute"]}
    assert {q["id"] for q in _liste(client, ident_assistant, relecture="brut")["questions"]} == {ids["brute"]}
    assert {q["id"] for q in _liste(client, ident_assistant, relecture="valide")["questions"]} == {ids["mienne"], ids["partagee"]}
    assert {q["id"] for q in _liste(client, ident_assistant, q="télétravail")["questions"]} == {ids["brute"]}
    assert _liste(client, ident_assistant, q="coffre")["questions"] == []  # la source illisible ne se devine pas par le texte
    page = _liste(client, ident_assistant, par_page=2)
    assert len(page["questions"]) == 2 and page["total"] == 3 and page["pages"] == 2


def test_peut_gerer_vient_du_serveur(client, en_tant_que, jeu, ident_assistant):
    ids = _monter(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])  # crée `mienne`, lit seulement `partagee`
    droits = {q["id"]: q["peut_gerer"] for q in _liste(client, ident_assistant)["questions"]}
    assert droits[ids["mienne"]] is True and droits[ids["partagee"]] is False


def test_la_synthese_par_source_lisible(client, en_tant_que, jeu, ident_assistant):
    _monter(client, en_tant_que, jeu, ident_assistant)
    en_tant_que(IDENTITES["alice"])
    corps = client.get(f"/api/assistants/{ident_assistant}/qualite").json()
    assert corps["seuil_fiable"] == 0.9
    par = {s["collection"]: s for s in corps["sources"]}
    assert set(par) == {jeu["mienne"], jeu["partagee"]}
    assert jeu["secrete"] not in str(corps)
    assert par[jeu["partagee"]]["reponses_fiables"] == 1 and par[jeu["partagee"]]["servie_fois"] == 0
    assert par[jeu["partagee"]]["synthese"]["questions"]["total"] == 2
    # Une fois servie, le compte monte.
    en_tant_que(SUPERADMIN)
    r = client.post(f"/api/v1/assistants/{ident_assistant}/executer", json={"question": QUESTIONS["partagee"][0]})
    assert r.status_code == 200 and r.json()["reponse"] == "Trente jours."
    en_tant_que(IDENTITES["alice"])
    par = {s["collection"]: s for s in client.get(f"/api/assistants/{ident_assistant}/qualite").json()["sources"]}
    assert par[jeu["partagee"]]["servie_fois"] == 1


def test_drapeau_assistants_faux_donne_404(client, en_tant_que, jeu, ident_assistant, capacites):
    _monter(client, en_tant_que, jeu, ident_assistant)
    capacites(assistants=False)
    en_tant_que(SUPERADMIN)
    assert client.get(f"/api/assistants/{ident_assistant}/qualite/questions").status_code == 404
    assert client.get(f"/api/assistants/{ident_assistant}/qualite").status_code == 404


def test_assistant_inconnu_404(client, en_tant_que):
    en_tant_que(SUPERADMIN)
    assert client.get("/api/assistants/n-existe-pas/qualite").status_code == 404
