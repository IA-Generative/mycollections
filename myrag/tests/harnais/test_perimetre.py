"""Le périmètre : pour chaque identité, les passages rendus sont ⊆ ce qu'elle lit. Une source
hors droit demandée par le client est ignorée, jamais citée. Un témoin négatif prouve que le test
voit la fuite quand le filtre est neutralisé."""

from __future__ import annotations

import pytest

from app.harnais import perimetre
from app.harnais.contrat import Etape, Plan
from tests.harnais.conftest import IDENTITES, LISIBLES, SOURCES_FICHE, passage


def _collections_vues(corps: dict) -> set[str]:
    return {r["context"]["collection"]["id"] for r in corps["results"]}


def verifier_pas_de_fuite(corps: dict, theatre, jeu: dict, identite: str) -> None:
    """Lève si un résultat vient d'une collection que `identite` ne lit pas, ou hors de la fiche ; ou si le
    connecteur a été interrogé sur une telle collection (même sans que rien n'en sorte)."""
    permis = {jeu[k] for k in LISIBLES[identite] if k in SOURCES_FICHE}
    vues = _collections_vues(corps)
    assert vues <= permis, f"fuite : {vues - permis}"
    interrogees = set(theatre.sources_appelees())
    assert interrogees <= permis, f"source hors droit interrogée : {interrogees - permis}"


@pytest.mark.parametrize("identite", ["alice", "bob", "superadmin"])
def test_les_passages_sont_inclus_dans_ce_que_la_personne_lit(client, en_tant_que, jeu, assistant_publie, theatre_branche, identite):
    en_tant_que(IDENTITES[identite])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 200, r.text
    corps = r.json()
    verifier_pas_de_fuite(corps, theatre_branche, jeu, identite)
    attendues = {jeu[k] for k in LISIBLES[identite] if k in SOURCES_FICHE}
    assert _collections_vues(corps) == attendues  # et rien de moins : toutes les sources lisibles répondent
    assert corps["plan"]["sources_ignorees"] == len(SOURCES_FICHE) - len(attendues)


def test_l_ouverte_n_est_pas_une_source_de_la_fiche(client, en_tant_que, jeu, assistant_publie, theatre_branche):
    """`ouverte` est lisible de tous mais n'est pas dans la fiche : l'assistant ne la cherche pas."""
    en_tant_que(IDENTITES["alice"])
    client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert jeu["ouverte"] not in theatre_branche.sources_appelees()


def test_une_personne_qui_ne_lit_aucune_source_ne_voit_pas_l_assistant(client, en_tant_que, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["dehors"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert theatre_branche.appels == []


def test_une_source_hors_droit_demandee_par_le_client_est_ignoree(client, en_tant_que, jeu, assistant_publie, theatre_branche):
    en_tant_que(IDENTITES["alice"])
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie, "scope": f"{jeu['secrete']},{jeu['mienne']}"})
    assert r.status_code == 200, r.text
    assert _collections_vues(r.json()) == {jeu["mienne"]}
    assert theatre_branche.sources_appelees() == [jeu["mienne"]]
    assert jeu["secrete"] not in r.text  # pas même nommée


def test_temoin_negatif_le_filtre_neutralise_la_fuite_est_detectee(client, en_tant_que, jeu, assistant_publie, theatre_branche, monkeypatch):
    """Sans filtre, Alice reçoit la collection de Bob : `verifier_pas_de_fuite` doit le voir."""
    en_tant_que(IDENTITES["alice"])
    monkeypatch.setattr(perimetre, "sources_lisibles", lambda fiche, collections, **_: [s.id for s in fiche.sources])
    monkeypatch.setattr(perimetre, "restreindre_passages", lambda passages, lisibles: list(passages))
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 200, r.text
    with pytest.raises(AssertionError, match="fuite|hors droit"):
        verifier_pas_de_fuite(r.json(), theatre_branche, jeu, "alice")


def test_le_dernier_filet_retire_un_passage_d_une_source_hors_perimetre(client, en_tant_que, jeu, assistant_publie, theatre_branche, monkeypatch):
    """Même si le périmètre du plan était trop large, `restreindre_passages` coupe la sortie."""
    en_tant_que(IDENTITES["alice"])
    monkeypatch.setattr(perimetre, "restreindre_plan", lambda plan, lisibles: plan)  # le plan garde l'étape `secrete`
    r = client.get("/api/v1/search", params={"q": "budget", "assistant": assistant_publie})
    assert r.status_code == 200
    assert jeu["secrete"] not in _collections_vues(r.json())


# ─── Fonctions pures ─────────────────────────────────────────────────────────────────────────


def test_restreindre_plan_retire_les_etapes_hors_droit_et_les_relais_qui_en_dependaient():
    plan = Plan(
        assistant="essai-assistant",
        version=1,
        planificateur="regles",
        etapes=[
            Etape(n=1, source="secrete", question="q"),
            Etape(n=2, source="ok", question="q"),
            Etape(n=3, source="ok2", question="q", attend=[1], avec="relais"),
            Etape(n=4, source="ok3", question="q", attend=[2], avec="relais"),
        ],
    )
    sortie = perimetre.restreindre_plan(plan, ["ok", "ok2", "ok3"])
    assert [e.n for e in sortie.etapes] == [2, 3, 4]
    assert sortie.etapes[1].attend == [] and sortie.etapes[1].avec is None  # sa source amont a disparu
    assert sortie.etapes[2].attend == [2] and sortie.etapes[2].avec == "relais"
    assert sortie.sources_ignorees == 1
    assert plan.sources_ignorees == 0  # le plan d'origine n'est pas modifié


def test_restreindre_passages():
    ps = [passage("a", "d", 1), passage("b", "d", 1), passage("a", "e", 2)]
    assert [(p.source, p.document) for p in perimetre.restreindre_passages(ps, ["a"])] == [("a", "d"), ("a", "e")]
    assert perimetre.restreindre_passages(ps, []) == []


def test_collection_lisible_ignore_l_archivee_et_l_inconnue():
    col = {"name": "c", "scope": "public", "scope_groups": [], "created_by": "x"}
    assert perimetre.collection_lisible(col, groupes=[], sub="y")
    assert not perimetre.collection_lisible({**col, "archived_at": "2026-01-01"}, groupes=[], sub="y")
    assert not perimetre.collection_lisible(None, groupes=[], sub="y")
    assert not perimetre.collection_lisible({**col, "scope": "private"}, groupes=[], sub="y")
    assert perimetre.collection_lisible({**col, "scope": "private"}, groupes=[], sub="x")  # le créateur
