"""La banque de questions d'une amorce : vingt questions, tenues à jour dans le jeu de questions.

Le jeu se crée au premier import et se MET À JOUR aux suivants quand le catalogue a changé — une
réponse attendue fausse (il y en avait, mesurées contre la source) se corrigeait sinon dans le
dépôt sans jamais atteindre la collection en service. Mais une question qu'un gestionnaire a
CORRIGÉE à la main (`modifie_le`) n'est plus réécrite par le catalogue : sa correction gagne.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.database import async_session
from app.models.db import PaireQA, utcnow

logger = logging.getLogger("myrag.amorces")

NOM_JEU = "Questions de test de l'amorce"  # gardé pour la migration des anciens jeux


async def poser_questions(collection: str, questions: list[dict]) -> int:
    """Crée les questions de l'amorce, ou les remet au niveau du catalogue ; rend leur nombre."""
    voulues = {
        f"amorce:{i + 1}": {
            "question": q["question"],
            "reponse": q.get("expected_answer", ""),
            "tags_json": json.dumps(q.get("tags", []), ensure_ascii=False),
            "must_cite_json": json.dumps(q.get("must_cite", []), ensure_ascii=False),
        }
        for i, q in enumerate(questions)
    }
    conflits = 0
    async with async_session() as s:
        r = await s.execute(select(PaireQA).where(PaireQA.collection_name == collection, PaireQA.origine == "amorce"))
        existantes = {q.source_ref: q for q in r.scalars().all() if q.source_ref and q.source_ref.startswith("amorce:")}
        for ref, champs in voulues.items():
            q = existantes.get(ref)
            if q is None:
                s.add(
                    PaireQA(
                        collection_name=collection,
                        source_ref=ref,
                        origine="amorce",
                        rang=int(ref.split(":")[1]),
                        contextes_json="[]",
                        relecture="valide" if champs["reponse"] else "brut",
                        relu_le=utcnow() if champs["reponse"] else None,
                        **champs,
                    )
                )
            elif q.modifie_le is None:
                for k, v in champs.items():
                    setattr(q, k, v)
            elif q.reponse != champs["reponse"]:
                conflits += 1
        for ref, q in existantes.items():
            if ref not in voulues and q.modifie_le is None:
                await s.delete(q)
        await s.commit()
    if conflits:
        logger.info("amorce %s : %d question(s) corrigée(s) à la main gardée(s) malgré le catalogue", collection, conflits)
    return len(voulues)
