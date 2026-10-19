"""La synthèse de qualité d'une collection, et ce qu'il y a à faire (docs/qualite.md).

Les « actions » sont des règles simples sur les comptes : elles disent au gestionnaire où
regarder (relire des questions, mesurer, traiter des avis, revoir le découpage ou les consignes).
"""

from __future__ import annotations

from datetime import timedelta

from app.models.db import utcnow
from app.models.qualite import ComptesQuestions, MesureFiche
from app.services import feedback_store, mesure_store, questions_store
from app.services.mesure.verdict import appreciation


def actions_suggerees(questions: ComptesQuestions, derniere: MesureFiche | None, satisfaction: dict, maintenant=None) -> list[dict]:
    maintenant = maintenant or utcnow()
    a: list[dict] = []
    total = questions.total
    validees = questions.par_relecture.get("valide", 0)
    a_relire = questions.par_relecture.get("brut", 0)
    if total == 0:
        a.append({"code": "constituer_jeu", "libelle": "Constituer le jeu de questions : faites-les rédiger d'après les documents, ou ajoutez les vôtres."})
    elif validees == 0:
        a.append({"code": "valider_questions", "libelle": f"Relire et valider les {a_relire} question(s) : seules les questions validées sont mesurées."})
    elif a_relire:
        a.append({"code": "valider_questions", "libelle": f"{a_relire} question(s) à relire dans le jeu."})
    if validees and (derniere is None or (derniere.cree_le and maintenant.isoformat() > (_date(derniere.cree_le) + timedelta(days=30)).isoformat())):
        a.append({"code": "lancer_mesure", "libelle": "Mesurer la qualité : aucune mesure récente."})
    if derniere and derniere.etat == "termine":
        vd = derniere.verdicts
        mesurees = max(1, derniere.nb_traitees or 0)
        echecs = vd.get("non_conformes", 0) + vd.get("partielles", 0)
        if echecs:
            a.append({"code": "corriger_echecs", "libelle": f"{echecs} question(s) mal répondues à la dernière mesure : voir pourquoi et corriger."})
        if (vd.get("sans_source", 0)) * 5 > mesurees:
            a.append({"code": "redecouper", "libelle": "Beaucoup de questions sans passage trouvé : le découpage des documents est peut-être à revoir."})
        if vd.get("refus_ko", 0):
            a.append({"code": "regle_de_garde", "libelle": "Une question hors sujet a reçu une réponse : ajouter une règle de garde aux consignes."})
    if satisfaction.get("pending_review"):
        a.append({"code": "traiter_avis", "libelle": f"{satisfaction['pending_review']} avis à relire : en faire des questions de référence."})
    return a


def _date(iso: str):
    from datetime import datetime

    return datetime.fromisoformat(iso)


async def synthese(name: str) -> dict:
    from app.services import generation_store

    questions = await questions_store.compter(name)
    mesures = await mesure_store.lister_mesures(name, limite=1)
    derniere = mesures[0] if mesures else None
    derniere_terminee = next((m for m in await mesure_store.lister_mesures(name, limite=10) if m.etat == "termine"), None)
    satisfaction = await feedback_store.feedback_stats(name)
    return {
        "questions": questions,
        "derniere_mesure": derniere,
        "derniere_terminee": derniere_terminee,
        "appreciation": appreciation(derniere_terminee.score if derniere_terminee else None),
        "tendance": await mesure_store.tendance(name),
        "satisfaction": satisfaction,
        "mesure_active": await mesure_store.mesure_active(name),
        "generation_active": await generation_store.run_actif(name),
        "actions": actions_suggerees(questions, derniere_terminee, satisfaction),
    }
