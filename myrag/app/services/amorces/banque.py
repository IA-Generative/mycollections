"""La banque de questions de test d'une amorce : vingt questions posées une fois."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.database import async_session
from app.models.db import EvalDataset

NOM_JEU = "Questions de test de l'amorce"


async def poser_questions(collection: str, questions: list[dict]) -> int:
    """Crée le jeu s'il n'existe pas ; rend le nombre de questions en banque pour ce jeu."""
    async with async_session() as session:
        existant = (await session.execute(
            select(EvalDataset).where(EvalDataset.collection_name == collection, EvalDataset.name == NOM_JEU)
        )).scalars().first()
        if existant:
            return len(json.loads(existant.questions_json or "[]"))
        normalisees = [
            {"id": f"amorce-{i + 1}", "question": q["question"], "expected_answer": q.get("expected_answer", ""),
             "tags": q.get("tags", []), "must_cite": q.get("must_cite", [])}
            for i, q in enumerate(questions)
        ]
        session.add(EvalDataset(
            collection_name=collection, name=NOM_JEU,
            description="Vingt questions écrites avec l'amorce, pour vérifier la collection dans le bac à sable (importées).",
            questions_json=json.dumps(normalisees, ensure_ascii=False),
        ))
        await session.commit()
        return len(normalisees)
