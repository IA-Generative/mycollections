"""Exécuter un run en tâche de fond : lire les passages, faire tourner ragas dans un fil, écrire.

Le fil de ragas ne touche jamais la base : il remplit un `Compteurs` (sous verrou), qu'une
coroutine recopie en base toutes les quelques secondes depuis la boucle du service. Un run à la
fois par processus (les autres attendent, visibles « en attente ») et un run actif par collection
(garde en base, 409). Pas d'annulation : un délai dépassé marque le run en erreur, mais le fil
termine sa phase en cours (docs/generation.md).
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings
from app.generation.morceaux import lire_echantillon, nombre_a_lire
from app.generation.resultats import Compteurs, PersonaDemande, ResultatGeneration, message_sur
from app.models.db import utcnow
from app.services import generation_store as store
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.generation")
# Le service ne configure pas de journal applicatif (seul uvicorn écrit) : sans ce gestionnaire,
# la ligne de bilan d'un run — exigée — n'apparaîtrait dans aucun journal du pod.
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
    """Un sémaphore par boucle (les tests en créent plusieurs ; en service, il n'y en a qu'une)."""
    boucle = id(asyncio.get_running_loop())
    if boucle not in _files:
        _files[boucle] = asyncio.Semaphore(1)
    return _files[boucle]


def generer_dans_le_fil(morceaux, personas, taille, distribution, compteurs: Compteurs) -> ResultatGeneration:
    """Le travail ragas, dans un fil. Les imports de ragas sont ici, pas au chargement du service."""
    from app.generation import modele, moteur

    rc = moteur.run_config_par_defaut(settings.generation_parallelisme, settings.generation_delai_appel_s)
    debit = modele.Debit(settings.generation_appels_par_minute)
    llm = modele.fabriquer_llm(compteurs, run_config=rc, debit=debit)
    emb = modele.fabriquer_embeddings(compteurs, run_config=rc, debit=debit)
    return moteur.generer(morceaux, personas, taille, llm, emb, distribution=distribution, run_config=rc, progression=compteurs.poser_phase)


def _compteurs_en_base(c: Compteurs) -> dict:
    return {k: v for k, v in c.instantane().items() if k != "duree_llm_s"}


async def _suivre(run_id: str, compteurs: Compteurs) -> None:
    while True:
        await asyncio.sleep(INTERVALLE_SUIVI_S)
        try:
            await store.maj_run(run_id, phase=compteurs.phase, **_compteurs_en_base(compteurs))
        except Exception as e:  # noqa: BLE001 — le suivi ne fait jamais échouer le run
            logger.warning("suivi du run %s : %s", run_id, type(e).__name__)


async def executer(run_id: str, name: str, personas: list[dict], taille: int, distribution: dict) -> None:
    debut = time.monotonic()
    compteurs = Compteurs()
    demandes = [PersonaDemande(p["nom"], p["description_role"]) for p in personas]
    suivi: asyncio.Task | None = None
    resultat = ResultatGeneration(etat="erreur")
    try:
        async with _file():
            await store.maj_run(run_id, etat="en_cours", phase="lecture", demarre_le=utcnow())
            n = nombre_a_lire(taille, settings.generation_morceaux_max)
            morceaux, nb_fichiers = await lire_echantillon(OpenRAGClient(timeout=60.0), name, n, graine=run_id)
            await store.maj_run(run_id, fichiers_collection=nb_fichiers, morceaux_envoyes=len(morceaux), phase="extraction")
            if not morceaux:
                resultat.erreur = "Aucun passage lisible dans cette collection."
            else:
                compteurs.poser_phase("extraction")
                suivi = asyncio.create_task(_suivre(run_id, compteurs))
                resultat = await asyncio.wait_for(
                    asyncio.to_thread(generer_dans_le_fil, morceaux, demandes, taille, distribution, compteurs), timeout=settings.generation_duree_max_s
                )
    except asyncio.TimeoutError:
        resultat = ResultatGeneration(etat="erreur", erreur=(f"Délai dépassé ({settings.generation_duree_max_s} s) : demandez moins de paires, ou réessayez."))
    except Exception as e:  # noqa: BLE001 — un run se termine toujours, motivé
        resultat = ResultatGeneration(etat="erreur", erreur=message_sur(e))
    finally:
        if suivi:
            suivi.cancel()

    duree = round(time.monotonic() - debut, 1)
    champs = {**_compteurs_en_base(compteurs), "duree_s": duree, "noeuds_avec_proprietes": resultat.noeuds_avec_proprietes or None}
    try:
        if resultat.etat == "termine":
            await store.maj_run(run_id, phase="enregistrement")
            n_paires = await store.enregistrer_paires(run_id, name, resultat.paires)
            await store.terminer_run(run_id, "termine", paires_obtenues=n_paires, paires_echouees=resultat.paires_echouees, **champs)
        else:
            await store.terminer_run(run_id, "erreur", erreur=resultat.erreur, paires_echouees=resultat.paires_echouees, **champs)
    except Exception as e:  # noqa: BLE001
        logger.error("run %s : écriture du résultat impossible (%s)", run_id, type(e).__name__)
        await store.terminer_run(run_id, "erreur", erreur=f"Résultat non enregistré : {type(e).__name__}")

    c = compteurs.instantane()
    # Une ligne par run, sans contenu : collection, taille, volumes, coût, durée.
    logger.info(
        "generation run=%s collection=%s etat=%s taille=%d passages=%s paires=%d echecs=%d appels_llm=%d tokens_entree=%d tokens_sortie=%d reparations_json=%d duree_s=%.1f",
        run_id,
        name,
        resultat.etat,
        taille,
        resultat.morceaux_envoyes,
        len(resultat.paires),
        resultat.paires_echouees,
        c["appels_llm"],
        c["tokens_entree"],
        c["tokens_sortie"],
        c["reparations_json"],
        duree,
    )
    try:
        from app.services.collectif_store import consigner

        type_ = "generation.terminee" if resultat.etat == "termine" else "generation.echouee"
        await consigner(
            "collection",
            name,
            type_,
            robot="generation",
            collection_name=name,
            detail={
                "run": run_id,
                "paires": len(resultat.paires),
                "appels_llm": c["appels_llm"],
                "tokens_entree": c["tokens_entree"],
                "tokens_sortie": c["tokens_sortie"],
                "duree_s": duree,
                **({"erreur": (resultat.erreur or "")[:300]} if resultat.etat != "termine" else {}),
            },
        )
    except Exception as e:  # noqa: BLE001 — le journal ne fait jamais échouer un run
        logger.warning("journal du run %s : %s", run_id, type(e).__name__)


def lancer(run: dict, name: str, personas: list[dict]) -> asyncio.Task:
    tache = asyncio.create_task(executer(run["id"], name, personas, run["taille"], run["distribution"]))
    _taches[run["id"]] = tache
    tache.add_done_callback(lambda _t: _taches.pop(run["id"], None))
    return tache
