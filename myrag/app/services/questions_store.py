"""Le jeu de questions de référence d'une collection (docs/qualite.md).

Une question de référence porte sa réponse (modifiable), son origine (générée par persona,
importée, saisie, tirée d'un avis, d'une amorce), son persona, ses passages, son statut de
relecture et deux drapeaux : `hors_sujet` (la bonne réponse est un refus) et `fiable` (la réponse
sera servie telle quelle, plus tard). Elle vit dans la table `paire_qa`.

Règles tenues ici, pas en SQL (portables SQLite et PostgreSQL) :
- modifier la question ou la réponse efface le dernier verdict : la mesure ne vaut plus ;
- `fiable` exige une question validée et pas hors sujet ; rejeter une question lui retire `fiable` ;
- un doublon (même question, à la casse et aux accents près) n'est pas réimporté.

Chaque fonction ouvre sa session ; les identités ne sont gardées qu'en condensé.
"""

from __future__ import annotations

import json
import re
import unicodedata
from math import ceil

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models.db import ORIGINES_QUESTION, RELECTURES_PAIRE, VERDICTS_MESURE, Feedback, PaireQA, utcnow
from app.services.collectif_store import Conflit, Introuvable, signature

QUESTION_MAX = 2000
REPONSE_MAX = 8000
IMPORT_MAX = 500
CHAMPS_MODIFIABLES = ("question", "reponse", "must_cite", "tags", "hors_sujet", "fiable", "relecture", "commentaire", "persona")


def condense(sub: str | None) -> str | None:
    return signature(sub).get("auteur_hash")


def plier(texte: str) -> str:
    """Une question comparable : minuscules, sans accents ni ponctuation, espaces réduits."""
    t = unicodedata.normalize("NFD", texte or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return " ".join(re.sub(r"[^\w]+", " ", t).split())


def _liste(v) -> list[str]:
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    return [str(x).strip()[:200] for x in (v or []) if str(x).strip()][:30]


def _verifier_textes(question: str | None, reponse: str | None) -> None:
    if question is not None and not (3 <= len(question.strip()) <= QUESTION_MAX):
        raise ValueError(f"La question doit faire de 3 à {QUESTION_MAX} caractères.")
    if reponse is not None and len(reponse) > REPONSE_MAX:
        raise ValueError(f"La réponse ne doit pas dépasser {REPONSE_MAX} caractères.")


def _appliquer_relecture(q: PaireQA, relecture: str, sub: str | None) -> None:
    if relecture not in RELECTURES_PAIRE:
        raise ValueError(f"relecture parmi {', '.join(RELECTURES_PAIRE)}")
    q.relecture = relecture
    q.relu_le = utcnow() if relecture != "brut" else None
    q.relu_par_hash = condense(sub) if relecture != "brut" else None
    if relecture != "valide":
        q.fiable = False


# ─── Lecture ──────────────────────────────────────────────────────────────────────


def _filtres(name: str, *, origine=None, relecture=None, fiable=None, hors_sujet=None, verdict=None, persona=None, texte=None, run_id=None) -> list:
    f = [PaireQA.collection_name == name]
    if origine:
        f.append(PaireQA.origine == origine)
    if relecture:
        f.append(PaireQA.relecture == relecture)
    if fiable is not None:
        f.append(PaireQA.fiable == fiable)
    if hors_sujet is not None:
        f.append(PaireQA.hors_sujet == hors_sujet)
    if verdict == "jamais":
        f.append(PaireQA.dernier_verdict.is_(None))
    elif verdict:
        f.append(PaireQA.dernier_verdict == verdict)
    if persona:
        f.append(PaireQA.persona_nom == persona)
    if run_id:
        f.append(PaireQA.run_id == run_id)
    if texte:
        motif = f"%{texte.strip()[:100]}%"
        f.append(or_(PaireQA.question.ilike(motif), PaireQA.reponse.ilike(motif)))
    return f


async def lister_questions(name: str, *, page: int = 1, par_page: int = 50, **filtres) -> dict:
    par_page = max(1, min(int(par_page), 200))
    conditions = _filtres(name, **filtres)
    async with async_session() as s:
        total = (await s.execute(select(func.count()).select_from(PaireQA).where(*conditions))).scalar_one()
        pages = max(1, ceil(total / par_page))
        page = max(1, min(int(page), pages))
        r = await s.execute(select(PaireQA).where(*conditions).order_by(PaireQA.cree_le.desc(), PaireQA.rang).offset((page - 1) * par_page).limit(par_page))
        return {"total": total, "page": page, "pages": pages, "par_page": par_page, "questions": [q.to_dict() for q in r.scalars().all()]}


async def lire_question(name: str, ident: str) -> dict:
    async with async_session() as s:
        q = await s.get(PaireQA, ident)
        if not q or q.collection_name != name:
            raise Introuvable("Question introuvable")
        return q.to_dict()


async def compter(name: str) -> dict:
    """Les comptes du jeu, par axe : de quoi résumer sans tout lire."""
    async with async_session() as s:

        async def par(colonne):
            r = await s.execute(select(colonne, func.count()).where(PaireQA.collection_name == name).group_by(colonne))
            return {(k if k is not None else "jamais"): n for k, n in r.all()}

        par_origine = await par(PaireQA.origine)
        par_relecture = await par(PaireQA.relecture)
        par_verdict = await par(PaireQA.dernier_verdict)
        fiables = (await s.execute(select(func.count()).where(PaireQA.collection_name == name, PaireQA.fiable.is_(True)))).scalar_one()
        hors = (await s.execute(select(func.count()).where(PaireQA.collection_name == name, PaireQA.hors_sujet.is_(True)))).scalar_one()
    return {
        "total": sum(par_origine.values()),
        "par_origine": par_origine,
        "par_relecture": par_relecture,
        "par_verdict": par_verdict,
        "fiables": fiables,
        "hors_sujet": hors,
    }


async def questions_a_mesurer(name: str, *, seulement_validees: bool = True, origines: list[str] | None = None) -> list[dict]:
    conditions = [PaireQA.collection_name == name, PaireQA.relecture != "rejete"]
    if seulement_validees:
        conditions.append(PaireQA.relecture == "valide")
    if origines:
        conditions.append(PaireQA.origine.in_(origines))
    async with async_session() as s:
        r = await s.execute(select(PaireQA).where(*conditions).order_by(PaireQA.cree_le))
        return [q.to_dict() for q in r.scalars().all()]


async def _questions_pliees(s, name: str) -> set[str]:
    r = await s.execute(select(PaireQA.question).where(PaireQA.collection_name == name, PaireQA.relecture != "rejete"))
    return {plier(q) for (q,) in r.all()}


# ─── Écriture ─────────────────────────────────────────────────────────────────────


def _nouvelle(name: str, champs: dict, sub: str | None, *, origine: str, source_ref=None, feedback_id=None) -> PaireQA:
    if origine not in ORIGINES_QUESTION:
        raise ValueError(f"origine parmi {', '.join(ORIGINES_QUESTION)}")
    question = str(champs.get("question") or "").strip()
    reponse = str(champs.get("reponse") or "").strip()
    _verifier_textes(question, reponse)
    q = PaireQA(
        collection_name=name,
        question=question,
        reponse=reponse,
        origine=origine,
        source_ref=source_ref,
        feedback_id=feedback_id,
        persona_nom=str(champs.get("persona") or "")[:120],
        must_cite_json=json.dumps(_liste(champs.get("must_cite")), ensure_ascii=False),
        tags_json=json.dumps(_liste(champs.get("tags")), ensure_ascii=False),
        hors_sujet=bool(champs.get("hors_sujet")),
        commentaire=str(champs.get("commentaire") or "")[:2000],
        contextes_json=json.dumps(champs.get("contextes") or [], ensure_ascii=False),
        relecture="brut",
    )
    relecture = champs.get("relecture") or "brut"
    _appliquer_relecture(q, relecture, sub)
    return q


async def creer_question(name: str, champs: dict, sub: str | None, *, origine: str = "saisie", source_ref: str | None = None, feedback_id: int | None = None) -> dict:
    async with async_session() as s:
        if plier(str(champs.get("question") or "")) in await _questions_pliees(s, name):
            raise Conflit("Cette question est déjà dans le jeu.")
        q = _nouvelle(name, champs, sub, origine=origine, source_ref=source_ref, feedback_id=feedback_id)
        s.add(q)
        try:
            await s.commit()
        except IntegrityError:
            raise Conflit("Cette question est déjà dans le jeu.")
        await s.refresh(q)
        return q.to_dict()


def normaliser_import(item: dict) -> dict | None:
    """Une entrée importée, aux deux formats acceptés : celui de l'assistant de création
    (`question`, `expected_answer`, `must_cite`, `tags`, `out_of_scope`) et celui de l'export
    eval-rag (`question`, `answer`, `persona_name`, `metadata`). None si inexploitable."""
    if not isinstance(item, dict):
        return None
    brut_meta = item.get("metadata")
    meta = brut_meta if isinstance(brut_meta, dict) else {}
    question = str(item.get("question") or item.get("user_input") or "").strip()
    if not question:
        return None
    reponse = str(item.get("reponse") or item.get("expected_answer") or item.get("answer") or item.get("reference") or "").strip()
    hors_sujet = bool(item.get("out_of_scope") or item.get("hors_sujet"))
    relecture = item.get("relecture") or meta.get("relecture")
    # Une question hors sujet est complète sans réponse : l'attendu est un refus.
    if relecture not in RELECTURES_PAIRE:
        relecture = "valide" if (reponse or hors_sujet) else "brut"
    if relecture == "valide" and not reponse and not hors_sujet:
        relecture = "brut"
    return {
        "question": question[:QUESTION_MAX],
        "reponse": reponse[:REPONSE_MAX],
        "must_cite": item.get("must_cite") or meta.get("must_cite") or [],
        "tags": item.get("tags") or meta.get("tags") or [],
        "hors_sujet": hors_sujet,
        "persona": item.get("persona") or item.get("persona_name") or "",
        "commentaire": item.get("note") or item.get("commentaire") or meta.get("commentaire") or "",
        "relecture": relecture,
    }


async def importer_questions(name: str, items: list, sub: str | None, *, origine: str = "importee", prefixe_ref: str | None = None) -> dict:
    """{crees, doublons, ignores}. Un doublon (déjà dans le jeu, ou deux fois dans le fichier)
    n'écrase rien ; une entrée sans question est ignorée."""
    if len(items) > IMPORT_MAX:
        raise ValueError(f"{IMPORT_MAX} questions au plus par import.")
    crees = doublons = ignores = 0
    async with async_session() as s:
        vues = await _questions_pliees(s, name)
        for rang, brut in enumerate(items):
            champs = normaliser_import(brut)
            if not champs:
                ignores += 1
                continue
            cle = plier(champs["question"])
            if cle in vues:
                doublons += 1
                continue
            try:
                q = _nouvelle(name, champs, sub, origine=origine, source_ref=f"{prefixe_ref}:{rang}" if prefixe_ref else None)
            except ValueError:
                ignores += 1
                continue
            q.rang = rang
            s.add(q)
            vues.add(cle)
            crees += 1
        await s.commit()
    return {"crees": crees, "doublons": doublons, "ignores": ignores}


async def modifier_question(name: str, ident: str, champs: dict, sub: str | None) -> dict:
    inconnus = set(champs) - set(CHAMPS_MODIFIABLES)
    if inconnus:
        raise ValueError(f"Champs non modifiables : {', '.join(sorted(inconnus))}")
    async with async_session() as s:
        q = await s.get(PaireQA, ident)
        if not q or q.collection_name != name:
            raise Introuvable("Question introuvable")
        _verifier_textes(champs.get("question"), champs.get("reponse"))
        texte_change = False
        for cle in ("question", "reponse"):
            if cle in champs and champs[cle] is not None and champs[cle].strip() != (getattr(q, cle) or ""):
                setattr(q, cle, champs[cle].strip())
                texte_change = True
        if texte_change:
            q.modifie_le, q.modifie_par_hash = utcnow(), condense(sub)
            q.dernier_verdict = None  # la mesure portait sur l'ancien texte
        if "must_cite" in champs:
            q.must_cite_json = json.dumps(_liste(champs["must_cite"]), ensure_ascii=False)
        if "tags" in champs:
            q.tags_json = json.dumps(_liste(champs["tags"]), ensure_ascii=False)
        if "persona" in champs and champs["persona"] is not None:
            q.persona_nom = str(champs["persona"])[:120]
        if "commentaire" in champs and champs["commentaire"] is not None:
            q.commentaire = str(champs["commentaire"])[:2000]
        if "hors_sujet" in champs and champs["hors_sujet"] is not None:
            q.hors_sujet = bool(champs["hors_sujet"])
            if q.hors_sujet:
                q.fiable = False
        if champs.get("relecture") is not None:
            _appliquer_relecture(q, champs["relecture"], sub)
        if champs.get("fiable") is not None:
            if champs["fiable"] and (q.relecture != "valide" or q.hors_sujet):
                raise Conflit("Seule une question validée, et pas hors sujet, peut avoir une réponse fiable.")
            q.fiable = bool(champs["fiable"])
        await s.commit()
        await s.refresh(q)
        return q.to_dict()


async def supprimer_question(name: str, ident: str) -> None:
    async with async_session() as s:
        q = await s.get(PaireQA, ident)
        if not q or q.collection_name != name:
            raise Introuvable("Question introuvable")
        await s.delete(q)
        await s.commit()


async def depuis_avis(name: str, feedback_id: int, reponse: str | None, sub: str | None) -> dict:
    """Un avis (souvent négatif) devient une question de référence : la question de l'usager,
    et la réponse corrigée par le gestionnaire (validée d'office si elle est fournie)."""
    async with async_session() as s:
        fb = await s.get(Feedback, feedback_id)
        if not fb or fb.collection_name != name:
            raise Introuvable("Avis introuvable")
        question = fb.question
    champs = {"question": question, "reponse": reponse or "", "relecture": "valide" if (reponse or "").strip() else "brut"}
    q = await creer_question(name, champs, sub, origine="avis", source_ref=f"feedback:{feedback_id}", feedback_id=feedback_id)
    async with async_session() as s:
        fb = await s.get(Feedback, feedback_id)
        if fb is not None:
            fb.status, fb.promoted_to, fb.reviewed_at = "promoted", "questions", utcnow()
            await s.commit()
    return q


async def noter_verdict(ident: str, verdict: str, mesure_id: str) -> None:
    if verdict not in VERDICTS_MESURE:
        raise ValueError(f"verdict parmi {', '.join(VERDICTS_MESURE)}")
    async with async_session() as s:
        q = await s.get(PaireQA, ident)
        if q:
            q.dernier_verdict, q.derniere_mesure_id, q.derniere_mesure_le = verdict, mesure_id, utcnow()
            await s.commit()
