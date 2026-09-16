"""La banque de questions de test d'une amorce : vingt questions, tenues à jour.

Le jeu se crée au premier import et se MET À JOUR aux suivants quand le catalogue
a changé — une réponse attendue fausse (il y en avait, mesurées contre la source)
se corrigeait sinon dans le dépôt sans jamais atteindre la collection en service.
Ce qu'une personne a ajouté à la main dans un AUTRE jeu n'est pas touché.
"""

from __future__ import annotations

import json

from sqlalchemy import select

from app.database import async_session
from app.models.db import EvalDataset

NOM_JEU = "Questions de test de l'amorce"


DESCRIPTION = ("Vingt questions écrites avec l'amorce, pour vérifier la collection dans le bac à sable "
               "(importées).")


def _normaliser(questions: list[dict]) -> list[dict]:
    return [
        {"id": f"amorce-{i + 1}", "question": q["question"], "expected_answer": q.get("expected_answer", ""),
         "tags": q.get("tags", []), "must_cite": q.get("must_cite", [])}
        for i, q in enumerate(questions)
    ]


async def poser_questions(collection: str, questions: list[dict]) -> int:
    """Crée le jeu, ou le remet au niveau du catalogue ; rend le nombre de questions."""
    normalisees = _normaliser(questions)
    async with async_session() as session:
        existant = (await session.execute(
            select(EvalDataset).where(EvalDataset.collection_name == collection, EvalDataset.name == NOM_JEU)
        )).scalars().first()
        if existant:
            if json.loads(existant.questions_json or "[]") != normalisees:
                existant.questions_json = json.dumps(normalisees, ensure_ascii=False)
                await session.commit()
            return len(normalisees)
        session.add(EvalDataset(
            collection_name=collection, name=NOM_JEU, description=DESCRIPTION,
            questions_json=json.dumps(normalisees, ensure_ascii=False),
        ))
        await session.commit()
        return len(normalisees)
