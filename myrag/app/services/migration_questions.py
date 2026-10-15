"""Verser les anciens magasins dans le jeu de questions de référence (docs/qualite.md).

Trois magasins tenaient des questions sans se parler :
- `eval_datasets` (jeux de test : banque du bac à sable, amorces, imports) ;
- les fichiers `data_dir/<collection>/qr_cache.json` (« réponses validées », jamais servies) ;
- les avis promus vers un jeu de test (`promoted_to = "eval"`), qui n'allaient nulle part.

La migration tourne à chaque démarrage et ne crée rien deux fois : chaque question versée porte une
`source_ref` (« eval:3:q1 », « qr:ab12cd34 », « feedback:12 ») unique par collection. Les tables
d'origine ne sont pas vidées (retour arrière possible) ; plus rien n'y écrit. Un fichier
`qr_cache.json` versé est renommé `qr_cache.migre.json`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.db import Collection, EvalDataset, Feedback, PaireQA, utcnow

logger = logging.getLogger("myrag.qualite")

NOM_JEU_AMORCE = "Questions de test de l'amorce"


def _origine_du_jeu(ds: EvalDataset) -> str:
    if ds.name == NOM_JEU_AMORCE:
        return "amorce"
    nom, desc = (ds.name or "").lower(), (ds.description or "").lower()
    if nom.endswith("-evaluation") or "genere" in desc or "auto" in nom:
        return "generee"
    return "importee"


def _question(collection: str, *, source_ref: str, question: str, reponse: str, origine: str, relecture: str, **autres) -> PaireQA:
    q = PaireQA(
        collection_name=collection,
        source_ref=source_ref,
        question=question.strip()[:2000],
        reponse=(reponse or "").strip()[:8000],
        origine=origine,
        relecture=relecture,
        contextes_json="[]",
        **autres,
    )
    if relecture != "brut":
        q.relu_le = utcnow()
    return q


async def _refs_existantes(s) -> set[tuple[str, str]]:
    r = await s.execute(select(PaireQA.collection_name, PaireQA.source_ref).where(PaireQA.source_ref.is_not(None)))
    return {(c, ref) for c, ref in r.all()}


async def migrer_eval_datasets() -> int:
    crees = 0
    async with async_session() as s:
        deja = await _refs_existantes(s)
        for ds in (await s.execute(select(EvalDataset))).scalars().all():
            origine = _origine_du_jeu(ds)
            for rang, item in enumerate(json.loads(ds.questions_json or "[]")):
                if not isinstance(item, dict) or not str(item.get("question") or "").strip():
                    continue
                ref = f"eval:{ds.id}:{item.get('id') or rang}"
                if (ds.collection_name, ref) in deja:
                    continue
                reponse = str(item.get("expected_answer") or "")
                hors = bool(item.get("out_of_scope"))
                # Une réponse écrite par une personne (amorce, import) est validée ; les questions
                # sans réponse de la banque auto-générée restent à relire.
                valide = origine in ("amorce", "importee") and (reponse.strip() or hors)
                s.add(
                    _question(
                        ds.collection_name,
                        source_ref=ref,
                        question=item["question"],
                        reponse=reponse,
                        origine=origine,
                        relecture="valide" if valide else "brut",
                        rang=rang,
                        hors_sujet=hors,
                        must_cite_json=json.dumps(item.get("must_cite") or [], ensure_ascii=False),
                        tags_json=json.dumps(item.get("tags") or [], ensure_ascii=False),
                        commentaire=str(item.get("note") or "")[:2000],
                    )
                )
                deja.add((ds.collection_name, ref))
                crees += 1
        await s.commit()
    return crees


async def migrer_qr_cache(data_dir: str | None = None) -> int:
    racine = Path(data_dir or settings.data_dir)
    crees = 0
    async with async_session() as s:
        collections = {n for (n,) in (await s.execute(select(Collection.name))).all()}
        deja = await _refs_existantes(s)
        for fichier in sorted(racine.glob("*/qr_cache.json")):
            nom = fichier.parent.name
            if nom not in collections:
                continue
            try:
                entrees = json.loads(fichier.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.warning("migration : %s illisible (%s)", fichier, type(e).__name__)
                continue
            promus = {}
            for fb in (await s.execute(select(Feedback).where(Feedback.collection_name == nom, Feedback.status == "promoted"))).scalars().all():
                promus.setdefault(fb.question.strip(), fb.id)
            for e in entrees if isinstance(entrees, list) else []:
                if not isinstance(e, dict) or not str(e.get("question") or "").strip():
                    continue
                ref = f"qr:{e.get('id') or e['question'][:40]}"
                if (nom, ref) in deja:
                    continue
                source = e.get("source") or "manual"
                origine = {"feedback": "avis", "import": "importee"}.get(source, "saisie")
                s.add(
                    _question(
                        nom,
                        source_ref=ref,
                        question=e["question"],
                        reponse=str(e.get("answer") or ""),
                        origine=origine,
                        relecture="valide",
                        tags_json=json.dumps(e.get("tags") or [], ensure_ascii=False),
                        # Seules les réponses corrigées par un gestionnaire (depuis un avis) sont fiables.
                        fiable=source == "feedback",
                        feedback_id=promus.get(e["question"].strip()) if source == "feedback" else None,
                    )
                )
                deja.add((nom, ref))
                crees += 1
            await s.commit()
            try:
                fichier.rename(fichier.with_name("qr_cache.migre.json"))
            except OSError as e:  # la base est à jour ; le fichier sera simplement relu (sans effet)
                logger.warning("migration : %s non renommé (%s)", fichier, type(e).__name__)
    return crees


async def migrer_avis_promus() -> int:
    crees = 0
    async with async_session() as s:
        deja = await _refs_existantes(s)
        r = await s.execute(select(Feedback).where(Feedback.status == "promoted", Feedback.promoted_to == "eval"))
        for fb in r.scalars().all():
            ref = f"feedback:{fb.id}"
            if (fb.collection_name, ref) in deja or not (fb.question or "").strip():
                continue
            s.add(_question(fb.collection_name, source_ref=ref, question=fb.question, reponse="", origine="avis", relecture="brut", feedback_id=fb.id))
            deja.add((fb.collection_name, ref))
            crees += 1
        await s.commit()
    return crees


async def migrer_vers_questions(data_dir: str | None = None) -> dict:
    """Les trois versements, dans l'ordre ; ne lève jamais (un démarrage ne doit pas tomber)."""
    bilan = {}
    for nom, etape in (("eval_datasets", migrer_eval_datasets), ("qr_cache", lambda: migrer_qr_cache(data_dir)), ("avis", migrer_avis_promus)):
        try:
            bilan[nom] = await etape()
        except Exception as e:  # noqa: BLE001
            logger.error("migration du jeu de questions, étape %s : %s", nom, e)
            bilan[nom] = -1
    if any(v for v in bilan.values()):
        logger.info("migration du jeu de questions : %s", bilan)
    return bilan
