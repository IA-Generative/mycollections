"""La banque de questions du bac à sable : le jeu de questions de la collection, plus les avis
négatifs pas encore traités (docs/qualite.md).

Lecture seule ; les écritures passent par /api/collections/{c}/qualite/questions (saisie, import,
validation, suppression, promotion d'un avis) et /api/feedback/ingest (👎).

Le champ `source` garde les quatre valeurs que l'écran connaît :
- `generated` : question générée (par persona, ou par la banque elle-même) ;
- `imported`  : importée, saisie ou venue d'une amorce ;
- `promoted`  : validée avec une réponse fiable, ou tirée d'un avis et validée ;
- `fb_neg`    : avis négatif encore à traiter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.database import async_session
from app.models.db import Feedback, PaireQA
from app.routers._droits import lire_la_collection

router = APIRouter(prefix="/api/playground", tags=["Playground"])


def source_de(q: PaireQA) -> str:
    if q.fiable or (q.origine == "avis" and q.relecture == "valide"):
        return "promoted"
    return "generated" if q.origine == "generee" else "imported"


@router.get("/{collection}/bank", dependencies=[Depends(lire_la_collection)])
async def get_bank(collection: str):
    """La banque agrégée. Vide est une réponse valable : l'appelant décide d'en générer."""
    items: list[dict] = []
    stats = {"total": 0, "generated": 0, "imported": 0, "fb_neg": 0, "promoted": 0}
    async with async_session() as session:
        r = await session.execute(select(PaireQA).where(PaireQA.collection_name == collection, PaireQA.relecture != "rejete").order_by(PaireQA.cree_le.desc()))
        for q in r.scalars().all():
            source = source_de(q)
            d = q.to_dict()
            items.append(
                {
                    "id": f"q_{q.id}",
                    "question": q.question,
                    "expected_answer": q.reponse,
                    "source": source,
                    "metadata": {
                        "question_id": q.id,
                        "origine": q.origine,
                        "relecture": q.relecture,
                        "fiable": d["fiable"],
                        "out_of_scope": d["hors_sujet"],
                        "must_cite": d["must_cite"],
                        "tags": d["tags"],
                        "persona": q.persona_nom,
                        "dernier_verdict": q.dernier_verdict,
                        "created_at": d["cree_le"],
                    },
                }
            )
            stats[source] += 1

        # Les avis négatifs pas encore traités (un avis promu est devenu une question).
        fb = await session.execute(
            select(Feedback).where(Feedback.collection_name == collection, Feedback.rating < 0, Feedback.status != "promoted").order_by(Feedback.created_at.desc())
        )
        for f in fb.scalars().all():
            items.append(
                {
                    "id": f"fb_{f.id}",
                    "question": f.question,
                    "expected_answer": "",
                    "source": "fb_neg",
                    "metadata": {
                        "feedback_id": f.id,
                        "rating": f.rating,
                        "reason": f.reason,
                        "response": f.response,
                        "status": f.status,
                        "owui_chat_id": f.owui_chat_id,
                        "created_at": f.created_at.isoformat() if f.created_at else "",
                    },
                }
            )
            stats["fb_neg"] += 1
    stats["total"] = len(items)
    return {"items": items, "stats": stats}
