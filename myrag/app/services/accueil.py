"""Ce que l'accueil raconte : à celui qui partage, ce que ses collections ont rendu
possible ; à celui qui découvre, une collection à essayer.

La mesure d'usage ne garde JAMAIS le texte d'une question : une collection, un instant,
un condensé d'identité (même sel que le bus). Seul le bac à sable y écrit aujourd'hui.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import timedelta

from sqlalchemy import func, select

from app.database import async_session
from app.models.db import Categorie, Collection, EvalDataset, Publication, Signalement, UsageQuestion, utcnow
from app.services import access
from app.services.nommage import titre_de
from app.services.pseudo import condenser

logger = logging.getLogger("myrag.accueil")

FENETRE_JOURS = 30
#: En dessous, on ne dit pas COMBIEN de personnes : trois questions de deux collègues, dans
#: un petit service, c'est déjà presque les nommer.
SEUIL_PERSONNES = 3


async def noter_question(collection: str, sub: str | None, canal: str = "bac-a-sable") -> None:
    """Best-effort : une mesure qui échoue ne prive personne de sa réponse."""
    try:
        try:
            auteur = condenser(sub) if sub else None
        except Exception:  # noqa: BLE001 — sel absent, sub inexploitable : la question compte quand même
            auteur = None
        async with async_session() as session:
            session.add(UsageQuestion(collection_name=collection, auteur_hash=auteur, canal=canal))
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("mesure d'usage non écrite pour %s : %s", collection, e)


async def mes_collections(sub: str, mon_hash: str) -> dict:
    """Les collections que je GÈRE (j'en suis le créateur ou le garant), avec ce que les
    AUTRES en ont fait sur la fenêtre : mes propres essais ne comptent pas."""
    depuis = utcnow() - timedelta(days=FENETRE_JOURS)
    async with async_session() as session:
        cols = (await session.execute(
            select(Collection).where(Collection.archived_at.is_(None))
            .where((Collection.created_by == sub) | (Collection.garant_hash == mon_hash))
            .order_by(Collection.name)
        )).scalars().all()
        if not cols:
            return {"collections": [], "fenetre_jours": FENETRE_JOURS, "actives": 0, "questions": 0, "personnes": None}
        noms = [c.name for c in cols]
        categories = {k.cle: k.libelle for k in (await session.execute(select(Categorie))).scalars().all()}
        publiees = set((await session.execute(
            select(Publication.collection_name).where(Publication.collection_name.in_(noms), Publication.state == "published")
        )).scalars().all())
        des_autres = (UsageQuestion.collection_name.in_(noms), UsageQuestion.cree_le >= depuis,
                      (UsageQuestion.auteur_hash.is_(None)) | (UsageQuestion.auteur_hash != mon_hash))
        questions = dict((await session.execute(
            select(UsageQuestion.collection_name, func.count()).where(*des_autres).group_by(UsageQuestion.collection_name)
        )).all())
        personnes = (await session.execute(
            select(func.count(func.distinct(UsageQuestion.auteur_hash))).where(*des_autres, UsageQuestion.auteur_hash.is_not(None))
        )).scalar() or 0
        signalements = dict((await session.execute(
            select(Signalement.collection_name, func.count())
            .where(Signalement.collection_name.in_(noms), Signalement.etat == "ouvert").group_by(Signalement.collection_name)
        )).all())

    lignes = [{
        "name": c.name, "titre": titre_de(c.to_dict()),
        "categorie": c.categorie, "categorie_libelle": categories.get(c.categorie or ""),
        "etat_collab": c.etat_collab, "publiee": c.name in publiees,
        "questions": questions.get(c.name, 0), "signalements_ouverts": signalements.get(c.name, 0),
    } for c in cols]
    lignes.sort(key=lambda l: (-l["questions"], l["titre"].lower()))
    return {
        "collections": lignes, "fenetre_jours": FENETRE_JOURS,
        "actives": sum(1 for l in lignes if l["publiee"]),
        "questions": sum(l["questions"] for l in lignes),
        "personnes": personnes if personnes >= SEUIL_PERSONNES else None,
        "signalements_ouverts": sum(l["signalements_ouverts"] for l in lignes),
    }


async def exemple(user_groups: list[str], user_sub: str, sauf: str | None = None) -> dict | None:
    """Une collection à essayer : publiée à tous, lisible par l'appelant, avec une question
    de SON JEU D'ÉVALUATION. Jamais une question posée par un utilisateur (avis, cache) :
    celles-là ne s'affichent pas sur une page d'accueil."""
    async with async_session() as session:
        cols = (await session.execute(
            select(Collection).where(Collection.archived_at.is_(None), Collection.etat_collab == "publiee_tous")
        )).scalars().all()
        lisibles = {c.name: c for c in cols if access.can_read(
            name=c.name, scope=c.scope, scope_groups=json.loads(c.scope_groups_json or "[]"),
            created_by=c.created_by, user_groups=user_groups, user_sub=user_sub)}
        if not lisibles:
            return None
        jeux = (await session.execute(select(EvalDataset).where(EvalDataset.collection_name.in_(list(lisibles))))).scalars().all()
        categories = {k.cle: k.libelle for k in (await session.execute(select(Categorie))).scalars().all()}
    questions: dict[str, list[str]] = {}
    for jeu in jeux:
        for q in json.loads(jeu.questions_json or "[]"):
            texte = (q.get("question") or "").strip()
            if texte and not q.get("out_of_scope") and len(texte) <= 160:
                questions.setdefault(jeu.collection_name, []).append(texte)
    candidates = [n for n in questions if n != sauf] or list(questions)
    if not candidates:
        return None
    name = random.choice(candidates)
    c = lisibles[name]
    return {"name": name, "titre": titre_de(c.to_dict()), "categorie": c.categorie,
            "categorie_libelle": categories.get(c.categorie or ""), "question": random.choice(questions[name]),
            "autres": len(candidates) > 1}
