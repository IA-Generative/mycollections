"""Exécuter une mesure en tâche de fond : chaque question posée à la collection, sa réponse
jugée, le verdict rangé, la synthèse écrite (docs/qualite.md).

Patron de la génération : une tâche asyncio par mesure, un registre, l'état en base suivi par
l'écran, une mesure à la fois par processus et une seule active par collection. Pas de fil :
répondre et juger sont asynchrones. Une question en échec n'arrête pas la mesure (verdict
`erreur`) ; un juge injoignable fait basculer la suite sur la similarité des textes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from app.config import settings
from app.generation.resultats import Compteurs, message_sur
from app.models.db import utcnow
from app.models.qualite import MesureFiche, QuestionFiche
from app.services import mesure_store as store
from app.services import questions_store
from app.services.mesure import juge as juge_mod
from app.services.mesure import verdict as v
from app.services.openrag_client import OpenRAGClient
from app.services.reponse import repondre

logger = logging.getLogger("myrag.qualite")
if not logger.handlers:
    _sortie = logging.StreamHandler()
    _sortie.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
    logger.addHandler(_sortie)
    logger.setLevel(logging.INFO)
    logger.propagate = False

INTERVALLE_SUIVI_S = 3.0
_taches: dict[str, asyncio.Task] = {}
_files: dict[int, asyncio.Semaphore] = {}


def _file() -> asyncio.Semaphore:
    boucle = id(asyncio.get_running_loop())
    if boucle not in _files:
        _files[boucle] = asyncio.Semaphore(1)
    return _files[boucle]


class _Etat:
    """Ce que la mesure accumule pendant qu'elle tourne (une seule boucle : pas de verrou)."""

    def __init__(self):
        self.verdicts: list[str] = []
        self.appels_chat = 0
        self.juge_ok = True
        self.methode_utilisee = "judge"
        self.jugements = 0


async def evaluer(name: str, q: QuestionFiche, *, client, compteurs: Compteurs, etat: _Etat, debit) -> dict:
    """Poser une question à la collection et juger la réponse ; rend le résultat (sans l'écrire)."""
    debut = time.monotonic()
    resultat = {
        "question_id": q.id,
        "question_texte": q.question,
        "reponse_reference": q.reponse or "",
        "hors_sujet": bool(q.hors_sujet),
        "persona_nom": q.persona or "",
        "origine": q.origine or "",
    }
    try:
        rep = await repondre(name, q.question, client=client)
        etat.appels_chat += 1
        resultat.update(reponse_obtenue=rep.contenu, repli=rep.repli, sources_json=json.dumps([{"fichier": n} for n in rep.source_names[:10]], ensure_ascii=False))
        methode = "judge"
        if q.hors_sujet:
            verdict, justification = v.verdict_hors_sujet(rep.contenu, rep.repli)
        elif not rep.sources or rep.repli == "fichiers":
            verdict, justification = "sans_source", "La collection n'a trouvé aucun passage pour répondre."
        elif not (q.reponse or "").strip():
            verdict, justification = "partiel", "Pas de réponse de référence : complétez-la pour une mesure exacte."
        else:
            jugement = None
            if etat.juge_ok:
                try:
                    jugement = await juge_mod.juger(q.question, q.reponse, rep.contenu, compteurs=compteurs, debit=debit)
                    etat.jugements += 1
                except juge_mod.JugeIndisponible:
                    etat.juge_ok = False  # inutile d'insister : la suite passe à la similarité
                except ValueError:
                    pass  # JSON illisible malgré la réparation : similarité pour CETTE question
            if jugement:
                verdict, justification = jugement.verdict, jugement.justification
            else:
                methode = "similarite"
                verdict, ratio = v.verdict_similarite(q.reponse, rep.contenu)
                justification = f"Comparaison des textes (juge indisponible) : {round(100 * ratio)} % de ressemblance."
            verdict, raison = v.plafonner(verdict, rep.contenu, q.must_cite or [])
            if raison:
                justification = f"{justification} {raison}".strip()
        resultat.update(verdict=verdict, justification=justification, score=v.score_de(verdict), methode=methode)
    except Exception as e:  # noqa: BLE001 — une question en échec n'arrête pas la mesure
        resultat.update(verdict="erreur", justification=message_sur(e), score=None, methode="judge")
    resultat["duree_s"] = round(time.monotonic() - debut, 2)
    return resultat


async def mesurer_une(name: str, mesure_id: str, q: QuestionFiche, *, client, compteurs: Compteurs, etat: _Etat, debit) -> str:
    resultat = await evaluer(name, q, client=client, compteurs=compteurs, etat=etat, debit=debit)
    await store.enregistrer_resultat(mesure_id, name, **resultat)
    if resultat["verdict"] != "erreur" and q.id:
        await questions_store.noter_verdict(q.id, resultat["verdict"], mesure_id)
    etat.verdicts.append(resultat["verdict"])
    return resultat["verdict"]


def _comptes(verdicts: list[str]) -> dict:
    c = lambda k: verdicts.count(k)  # noqa: E731
    return {
        "nb_conformes": c("conforme"),
        "nb_partielles": c("partiel"),
        "nb_non_conformes": c("non_conforme"),
        "nb_refus_ok": c("refus_ok"),
        "nb_refus_ko": c("refus_ko"),
        "nb_sans_source": c("sans_source"),
        "nb_erreurs": c("erreur"),
    }


async def _suivre(mesure_id: str, etat: _Etat, compteurs: Compteurs) -> None:
    while True:
        await asyncio.sleep(INTERVALLE_SUIVI_S)
        try:
            c = compteurs.instantane()
            await store.maj_mesure(
                mesure_id,
                nb_traitees=len(etat.verdicts),
                appels_chat=etat.appels_chat,
                appels_llm=c["appels_llm"],
                tokens_entree=c["tokens_entree"],
                tokens_sortie=c["tokens_sortie"],
                **_comptes(etat.verdicts),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("suivi de la mesure %s : %s", mesure_id, type(e).__name__)


async def executer(mesure_id: str, name: str, questions: list[QuestionFiche]) -> None:
    from app.services.debit import partage

    debut = time.monotonic()
    compteurs, etat = Compteurs(), _Etat()
    suivi = None
    erreur = None
    try:
        async with _file():
            await store.maj_mesure(mesure_id, etat="en_cours", phase="reponses", demarre_le=utcnow())
            client = OpenRAGClient(timeout=float(settings.mesure_delai_appel_s))
            if not await client.health_check():
                raise RuntimeError("OpenRAG n'est pas accessible : la collection ne peut pas répondre.")
            suivi = asyncio.create_task(_suivre(mesure_id, etat, compteurs))
            parallele = asyncio.Semaphore(max(1, settings.mesure_parallelisme))
            debit = partage()

            async def une(q):
                async with parallele:
                    await mesurer_une(name, mesure_id, q, client=client, compteurs=compteurs, etat=etat, debit=debit)

            await asyncio.wait_for(asyncio.gather(*(une(q) for q in questions)), timeout=settings.mesure_duree_max_s)
    except asyncio.TimeoutError:
        erreur = f"Délai dépassé ({settings.mesure_duree_max_s} s) : mesurez moins de questions."
    except Exception as e:  # noqa: BLE001
        erreur = message_sur(e) if not isinstance(e, RuntimeError) else str(e)
    finally:
        if suivi:
            suivi.cancel()

    duree = round(time.monotonic() - debut, 1)
    c = compteurs.instantane()
    score = v.score_global(etat.verdicts)
    methode = "judge" if etat.jugements else "similarite"
    champs = {
        "nb_traitees": len(etat.verdicts),
        "appels_chat": etat.appels_chat,
        "appels_llm": c["appels_llm"],
        "tokens_entree": c["tokens_entree"],
        "tokens_sortie": c["tokens_sortie"],
        "erreurs_llm": c["erreurs_llm"],
        "refus_debit": c["refus_debit"],
        "duree_s": duree,
        "score": score,
        "methode": methode,
        **_comptes(etat.verdicts),
    }
    if erreur is None and etat.verdicts and all(x == "erreur" for x in etat.verdicts):
        erreur = "Aucune question n'a pu être mesurée : la collection ou le modèle ne répond pas."
    await store.terminer_mesure(mesure_id, "erreur" if erreur else "termine", erreur=erreur, **champs)
    logger.info(
        "mesure id=%s collection=%s etat=%s questions=%d score=%s methode=%s appels_chat=%d appels_llm=%d tokens=%d duree_s=%.1f",
        mesure_id,
        name,
        "erreur" if erreur else "termine",
        len(questions),
        score,
        methode,
        etat.appels_chat,
        c["appels_llm"],
        c["tokens_entree"] + c["tokens_sortie"],
        duree,
    )
    try:
        from app.services.collectif_store import consigner

        await consigner(
            "collection",
            name,
            "mesure.echouee" if erreur else "mesure.terminee",
            robot="mesure",
            collection_name=name,
            detail={"mesure": mesure_id, "score": score, "questions": len(questions), "duree_s": duree, **({"erreur": erreur[:300]} if erreur else {})},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("journal de la mesure %s : %s", mesure_id, type(e).__name__)


def lancer(mesure: MesureFiche, name: str, questions: list[QuestionFiche]) -> asyncio.Task:
    tache = asyncio.create_task(executer(mesure.id, name, questions))
    _taches[mesure.id] = tache
    tache.add_done_callback(lambda _t: _taches.pop(mesure.id, None))
    return tache


async def tester_une(name: str, q: QuestionFiche) -> dict:
    """Re-tester une seule question, tout de suite (volet d'une question) : rien n'est enregistré."""
    from app.services.debit import partage

    client = OpenRAGClient(timeout=float(settings.mesure_delai_appel_s))
    r = await evaluer(name, q, client=client, compteurs=Compteurs(), etat=_Etat(), debit=partage())
    return {
        "verdict": r["verdict"],
        "justification": r["justification"],
        "reponse_obtenue": r.get("reponse_obtenue", ""),
        "sources": json.loads(r.get("sources_json") or "[]"),
        "repli": r.get("repli", "aucun"),
        "methode": r.get("methode"),
    }
