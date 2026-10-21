"""Le journal d'un plan : une ligne de `plans_journal` par recherche, jamais un texte libre.

Ni la question, ni un passage, ni une réponse : des identifiants, des poids, des durées, des
compteurs (`JournalPlan` n'a aucun champ de texte). C'est le seul module du harnais qui touche
à la base, par la couche de stockage existante (`app.database.async_session`)."""

from __future__ import annotations

import json
import logging

from app.database import async_session
from app.harnais.contrat import Canal, FicheAssistant, JournalPlan, Plan, canonique, empreinte
from app.harnais.execution import Execution
from app.models.db import PlanJournal

logger = logging.getLogger("myrag.harnais")


def construire(
    plan: Plan,
    fiche: FicheAssistant,
    execution: Execution,
    *,
    canal: Canal,
    auteur_hash: str | None = None,
    robot: str | None = None,
    duree_ms: int | None = None,
) -> JournalPlan:
    return JournalPlan(
        assistant=plan.assistant,
        version=plan.version,
        empreinte=empreinte(canonique(fiche)),
        canal=canal,
        planificateur=plan.planificateur,
        consigne=plan.consigne,
        score_consigne=plan.score_consigne,
        reponse_fiable=plan.reponse_fiable is not None,
        a_valider=plan.a_valider,
        sources_ignorees=plan.sources_ignorees + execution.sources_ignorees,
        etapes=execution.journal_etapes(),
        duree_ms=execution.duree_ms if duree_ms is None else duree_ms,
        auteur_hash=auteur_hash,
        robot=robot,
    )


async def ecrire(j: JournalPlan) -> None:
    """Écrit le journal ; une panne de journal ne fait jamais échouer la recherche."""
    try:
        async with async_session() as s:
            s.add(
                PlanJournal(
                    assistant_id=j.assistant,
                    version=j.version,
                    empreinte=j.empreinte,
                    canal=j.canal,
                    planificateur=j.planificateur,
                    consigne=j.consigne,
                    score_consigne=j.score_consigne,
                    reponse_fiable=j.reponse_fiable,
                    a_valider=j.a_valider,
                    valide=j.valide,
                    sources_ignorees=j.sources_ignorees,
                    nb_etapes=len(j.etapes),
                    nb_passages=sum(e.passages for e in j.etapes),
                    etapes_json=json.dumps([e.model_dump(mode="json") for e in j.etapes], ensure_ascii=False),
                    duree_ms=j.duree_ms,
                    auteur_hash=j.auteur_hash,
                    robot=j.robot,
                )
            )
            await s.commit()
    except Exception:
        logger.warning("Journal du plan non écrit (assistant=%s)", j.assistant, exc_info=False)
