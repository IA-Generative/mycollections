"""Les anciens magasins versés dans le jeu de questions : une fois, sans doublon, avec la bonne
origine et le bon statut ; le fichier qr_cache.json renommé ; une seconde passe ne crée rien."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.db import EvalDataset, Feedback, PaireQA
from app.services.migration_questions import NOM_JEU_AMORCE, migrer_vers_questions


async def _semer(nom: str) -> int:
    async with async_session() as s:
        s.add_all(
            [
                EvalDataset(
                    collection_name=nom,
                    name=NOM_JEU_AMORCE,
                    description="",
                    questions_json=json.dumps([{"id": "amorce-1", "question": "Libellé NATINF 7987 ?", "expected_answer": "Pêche maritime", "must_cite": ["7987"]}]),
                ),
                EvalDataset(
                    collection_name=nom,
                    name=f"{nom}-evaluation",
                    description="Jeu de test genere automatiquement",
                    questions_json=json.dumps(
                        [
                            {"id": "auto-1", "question": "Question auto ?", "expected_answer": ""},
                            {"id": "hs", "question": "Âge du capitaine ?", "expected_answer": "", "out_of_scope": True},
                        ]
                    ),
                ),
                EvalDataset(
                    collection_name=nom,
                    name="mon import",
                    description="",
                    questions_json=json.dumps([{"id": "i1", "question": "Question importée ?", "expected_answer": "Réponse importée", "note": "à revoir"}]),
                ),
            ]
        )
        fb = Feedback(collection_name=nom, question="Avis promu vers un jeu ?", response="x", rating=-1, status="promoted", promoted_to="eval")
        fbq = Feedback(collection_name=nom, question="Promu question ?", response="x", rating=-1, status="promoted", promoted_to="qr")
        s.add_all([fb, fbq])
        await s.commit()
        return fbq.id


def test_migration_des_trois_magasins(creer_collection, nom):
    creer_collection(nom)
    id_promu = asyncio.run(_semer(nom))
    dossier = Path(settings.data_dir) / nom
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "qr_cache.json").write_text(
        json.dumps(
            [
                {"id": "ab12cd34", "question": "Promu question ?", "answer": "Bonne réponse corrigée", "tags": [], "source": "feedback"},
                {"id": "ef56", "question": "Validée en bac à sable ?", "answer": "Réponse du RAG", "tags": ["x"], "source": "manual"},
            ]
        ),
        encoding="utf-8",
    )

    asyncio.run(migrer_vers_questions())
    second = asyncio.run(migrer_vers_questions())
    assert second == {"eval_datasets": 0, "qr_cache": 0, "avis": 0}

    async def lire():
        async with async_session() as s:
            r = await s.execute(select(PaireQA).where(PaireQA.collection_name == nom))
            return {q.question: q for q in r.scalars().all()}

    jeu = asyncio.run(lire())
    assert len(jeu) == 7

    amorce = jeu["Libellé NATINF 7987 ?"]
    assert (amorce.origine, amorce.relecture, json.loads(amorce.must_cite_json)) == ("amorce", "valide", ["7987"])
    assert (jeu["Question auto ?"].origine, jeu["Question auto ?"].relecture) == ("generee", "brut")
    assert jeu["Âge du capitaine ?"].hors_sujet is True
    imp = jeu["Question importée ?"]
    assert (imp.origine, imp.relecture, imp.commentaire) == ("importee", "valide", "à revoir")
    promu = jeu["Promu question ?"]
    assert (promu.origine, promu.relecture, promu.fiable, promu.feedback_id) == ("avis", "valide", True, id_promu)
    manuel = jeu["Validée en bac à sable ?"]
    assert (manuel.origine, manuel.relecture, manuel.fiable) == ("saisie", "valide", False)
    avis = jeu["Avis promu vers un jeu ?"]
    assert (avis.origine, avis.relecture, avis.reponse) == ("avis", "brut", "")
    assert not (dossier / "qr_cache.json").exists() and (dossier / "qr_cache.migre.json").exists()
