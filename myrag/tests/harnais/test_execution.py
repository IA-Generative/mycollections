"""L'exécution d'un plan : parallèle, relais, sources en panne, connecteur OpenRAG."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.harnais.connecteurs.openrag import ConnecteurOpenRAG
from app.harnais.contrat import Appelant, Etape, Plan
from app.harnais.execution import executer, meilleur
from app.services.openrag_client import ResultatRecherche
from tests.harnais.conftest import Theatre, passage

PERSONNE = Appelant(sub="personne-x", groupes=[])


def _plan(*etapes: Etape) -> Plan:
    return Plan(assistant="essai-assistant", version=1, planificateur="toutes_les_sources", etapes=list(etapes))


def _erreur_http(statut: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError("erreur", request=httpx.Request("GET", "http://openrag"), response=httpx.Response(statut))


@pytest.mark.asyncio
async def test_les_etapes_independantes_partent_ensemble():
    theatre = Theatre({"s1": [passage("s1", "a", 1)], "s2": [passage("s2", "b", 1)]})
    theatre.barriere = asyncio.Event()  # personne ne repart tant que les deux ne sont pas entrées
    theatre.attendus = 2
    plan = _plan(Etape(n=1, source="s1", question="budget"), Etape(n=2, source="s2", question="budget"))
    tache = asyncio.ensure_future(executer(plan, {"s1": theatre, "s2": theatre}, PERSONNE))
    await asyncio.wait_for(theatre.entrees_vues.wait(), timeout=2)  # sinon : exécution séquentielle
    assert sorted(theatre.entrees) == [1, 2] and not tache.done()
    theatre.barriere.set()
    execution = await asyncio.wait_for(tache, timeout=2)
    assert {n: len(p) for n, p in execution.par_etape.items()} == {1: 1, 2: 1}


@pytest.mark.asyncio
async def test_une_etape_qui_attend_recoit_le_meilleur_passage_de_celles_qu_elle_attend():
    theatre = Theatre(
        {
            "s1": [passage("s1", "faible", 1, score=0.4), passage("s1", "fort", 2, score=0.9)],
            "s2": [passage("s2", "c", 1)],
            "s3": [passage("s3", "d", 1)],
        }
    )
    plan = _plan(
        Etape(n=1, source="s1", question="q"),
        Etape(n=2, source="s2", question="q"),
        Etape(n=3, source="s3", question="q", attend=[1, 2], avec="article_trouve"),
    )
    await executer(plan, dict.fromkeys(("s1", "s2", "s3"), theatre), PERSONNE)
    assert theatre.entrees[-1] == 3  # la dernière attend les deux premières
    amont = next(a for n, _, a in theatre.appels if n == 3)
    assert [p.document for p in amont] == ["fort", "c"]  # le meilleur de chaque étape attendue
    assert next(a for n, _, a in theatre.appels if n == 1) == ()


def test_le_meilleur_passage_prefere_le_score_puis_le_rang():
    assert meilleur([]) is None
    a, b = passage("s", "a", 1, score=0.2), passage("s", "b", 2, score=0.8)
    assert meilleur([a, b]) is b
    sans_score = [passage("s", "x", 1), passage("s", "y", 2)]
    assert meilleur(sans_score).document == "x"


@pytest.mark.asyncio
async def test_une_source_en_5xx_est_ignoree_et_comptee_les_autres_repondent():
    theatre = Theatre({"s1": [passage("s1", "a", 1)], "s2": [], "s3": [passage("s3", "c", 1)]}, pannes={"s2": _erreur_http(503)})
    plan = _plan(*(Etape(n=i, source=f"s{i}", question="q") for i in (1, 2, 3)))
    execution = await executer(plan, dict.fromkeys(("s1", "s2", "s3"), theatre), PERSONNE)
    assert execution.sources_ignorees == 1
    assert execution.sorties[2].erreur == "panne" and execution.sorties[2].passages == []
    assert execution.sorties[1].erreur is None and execution.sorties[3].erreur is None
    assert not execution.toutes_en_panne
    assert [e.erreur for e in execution.journal_etapes()] == [None, "panne", None]


@pytest.mark.asyncio
async def test_un_refus_un_delai_et_une_source_sans_connecteur_sont_ignores():
    theatre = Theatre({"s1": [passage("s1", "a", 1)]}, pannes={"s2": _erreur_http(404), "s3": asyncio.TimeoutError()})
    plan = _plan(*(Etape(n=i, source=f"s{i}", question="q") for i in (1, 2, 3, 4)))
    execution = await executer(plan, dict.fromkeys(("s1", "s2", "s3"), theatre), PERSONNE)
    assert [execution.sorties[n].erreur for n in (1, 2, 3, 4)] == [None, "refus", "delai", "refus"]
    assert execution.sources_ignorees == 3


@pytest.mark.asyncio
async def test_toutes_en_panne():
    theatre = Theatre(pannes={"s1": _erreur_http(500), "s2": httpx.ConnectError("coupé")})
    plan = _plan(Etape(n=1, source="s1", question="q"), Etape(n=2, source="s2", question="q"))
    execution = await executer(plan, {"s1": theatre, "s2": theatre}, PERSONNE)
    assert execution.toutes_en_panne and execution.sources_ignorees == 2


@pytest.mark.asyncio
async def test_une_source_qui_ne_trouve_rien_n_est_pas_ignoree():
    theatre = Theatre({"s1": []})
    execution = await executer(_plan(Etape(n=1, source="s1", question="q")), {"s1": theatre}, PERSONNE)
    assert execution.sorties[1].erreur == "vide" and execution.sources_ignorees == 0 and not execution.toutes_en_panne


@pytest.mark.asyncio
async def test_un_passage_d_une_autre_source_que_celle_de_l_etape_est_ecarte():
    theatre = Theatre({"s1": [passage("s1", "a", 1), passage("autre", "z", 2)]})
    execution = await executer(_plan(Etape(n=1, source="s1", question="q")), {"s1": theatre}, PERSONNE)
    assert [p.source for p in execution.sorties[1].passages] == ["s1"]


# ─── Le connecteur OpenRAG : jamais de liste vide, une requête multi-partitions ──────────────


def _doc(partition: str, file_id: str, chunk: int, contenu: str = "Le budget est voté en janvier.", **meta) -> dict:
    return {
        "link": f"http://openrag:8080/extract/{chunk}",
        "content": contenu,
        "metadata": {"partition": partition, "file_id": file_id, "_id": chunk, "filename": f"{file_id}.md", **meta},
    }


@pytest.fixture
def openrag():
    with patch("app.harnais.connecteurs.openrag.OpenRAGClient") as cls:
        cls.return_value.search = AsyncMock(return_value=ResultatRecherche(documents=[]))
        yield cls.return_value.search


@pytest.mark.asyncio
async def test_une_liste_de_partitions_vide_n_est_jamais_envoyee(openrag):
    conn = ConnecteurOpenRAG()
    assert await executer(_plan(), {}, PERSONNE) is not None  # un plan sans étape n'appelle rien
    assert await conn._rechercher([], "q") == []
    assert await conn.chercher_groupe([], PERSONNE) == {}
    openrag.assert_not_called()


@pytest.mark.asyncio
async def test_des_etapes_independantes_de_meme_question_font_une_seule_requete(openrag):
    openrag.return_value = ResultatRecherche(
        documents=[_doc("p1", "d1", 1, relevance_score=0.9), _doc("p2", "d2", 2, relevance_score=0.8), _doc("p1", "d3", 3, relevance_score=0.7), _doc("hors", "dx", 9)]
    )
    conn = ConnecteurOpenRAG(top_k=30)
    plan = _plan(Etape(n=1, source="p1", question="budget"), Etape(n=2, source="p2", question="budget"))
    execution = await executer(plan, {"p1": conn, "p2": conn}, PERSONNE)
    assert openrag.await_count == 1
    assert openrag.await_args.args[0] == ["p1", "p2"] and openrag.await_args.kwargs["top_k"] == 30
    assert [p.document for p in execution.sorties[1].passages] == ["d1", "d3"]
    assert [p.rang for p in execution.sorties[1].passages] == [1, 2]
    assert [p.document for p in execution.sorties[2].passages] == ["d2"]  # « hors » n'est à aucune étape : écarté


@pytest.mark.asyncio
async def test_si_l_appel_groupe_echoue_chaque_etape_reprend_seule(openrag):
    async def selon(partitions, question, top_k=5):
        if len(partitions) > 1 or partitions[0] == "p2":
            raise _erreur_http(500 if len(partitions) > 1 else 503)
        return ResultatRecherche(documents=[_doc("p1", "d1", 1)])

    openrag.side_effect = selon
    conn = ConnecteurOpenRAG()
    plan = _plan(Etape(n=1, source="p1", question="budget"), Etape(n=2, source="p2", question="budget"))
    execution = await executer(plan, {"p1": conn, "p2": conn}, PERSONNE)
    assert [c.args[0] for c in openrag.await_args_list] == [["p1", "p2"], ["p1"], ["p2"]]
    assert [p.document for p in execution.sorties[1].passages] == ["d1"]
    assert execution.sorties[2].erreur == "panne" and execution.sources_ignorees == 1


@pytest.mark.asyncio
async def test_le_relais_precise_la_question_de_l_etape_qui_a_un_avec(openrag):
    openrag.return_value = ResultatRecherche(documents=[_doc("p1", "d1", 1, "Article 12 : le droit de séjour.")])
    conn = ConnecteurOpenRAG()
    plan = _plan(Etape(n=1, source="p1", question="séjour"), Etape(n=2, source="p2", question="et ses décrets ?", attend=[1], avec="article_trouve"))
    await executer(plan, {"p1": conn, "p2": conn}, PERSONNE)
    question_etape_2 = openrag.await_args_list[1].args[1]
    assert question_etape_2.startswith("et ses décrets ?") and "Article 12" in question_etape_2


def test_un_morceau_sans_partition_ou_sans_texte_n_est_pas_un_passage():
    from app.harnais.connecteurs.openrag import vers_passage
    from app.services.openrag_client import DocumentRecherche

    assert vers_passage(DocumentRecherche(content="texte", metadata={}), etape=1, rang=1) is None
    assert vers_passage(DocumentRecherche(content="   ", metadata={"partition": "p"}), etape=1, rang=1) is None
    p = vers_passage(DocumentRecherche.model_validate(_doc("p", "d", 7, relevance_score=0.5, page=3)), etape=2, rang=4)
    assert (p.source, p.etape, p.rang, p.score, p.ident, p.document, p.titre, p.page) == ("p", 2, 4, 0.5, "7", "d", "d", 3)
