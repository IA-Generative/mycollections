"""Accès en base des mesures de qualité (docs/qualite.md). Patron de generation_store."""

from __future__ import annotations

import json
from math import ceil

from sqlalchemy import delete, func, select

from app.database import async_session
from app.models.db import Mesure, MesureResultat, utcnow
from app.models.qualite import MesureFiche, PageResultats, ResultatFiche, ResultatVolet, TendanceFiche
from app.services.collectif_store import Conflit, Introuvable, signature

ACTIVES = ("en_attente", "en_cours")


async def mesure_active(name: str) -> MesureFiche | None:
    async with async_session() as s:
        m = (await s.execute(select(Mesure).where(Mesure.collection_name == name, Mesure.etat.in_(ACTIVES)))).scalars().first()
        return MesureFiche.depuis(m) if m else None


async def creer_mesure(name: str, filtre: dict, modele: str, nb_questions: int, sub: str | None) -> MesureFiche:
    if await mesure_active(name):
        raise Conflit("Une mesure est déjà en cours pour cette collection.")
    async with async_session() as s:
        m = Mesure(collection_name=name, filtre_json=json.dumps(filtre), modele=modele, nb_questions=nb_questions, lance_par_hash=signature(sub).get("auteur_hash"))
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return MesureFiche.depuis(m)


async def lister_mesures(name: str, limite: int = 50) -> list[MesureFiche]:
    async with async_session() as s:
        r = await s.execute(select(Mesure).where(Mesure.collection_name == name).order_by(Mesure.cree_le.desc()).limit(limite))
        return [MesureFiche.depuis(m) for m in r.scalars().all()]


async def lire_mesure(name: str, ident: str) -> MesureFiche:
    async with async_session() as s:
        m = await s.get(Mesure, ident)
        if not m or m.collection_name != name:
            raise Introuvable("Mesure introuvable")
        return MesureFiche.depuis(m)


async def maj_mesure(ident: str, **champs) -> None:
    async with async_session() as s:
        m = await s.get(Mesure, ident)
        if m:
            for k, v in champs.items():
                if hasattr(m, k) and v is not None:
                    setattr(m, k, v)
            await s.commit()


async def terminer_mesure(ident: str, etat: str, *, erreur: str | None = None, **champs) -> MesureFiche | None:
    async with async_session() as s:
        m = await s.get(Mesure, ident)
        if not m:
            return None
        for k, v in champs.items():
            if hasattr(m, k) and v is not None:
                setattr(m, k, v)
        m.etat, m.phase, m.termine_le = etat, "fini", utcnow()
        m.erreur = (erreur or "Échec sans message") if etat == "erreur" else None
        await s.commit()
        await s.refresh(m)
        return MesureFiche.depuis(m)


async def enregistrer_resultat(mesure_id: str, name: str, **champs) -> None:
    async with async_session() as s:
        s.add(MesureResultat(mesure_id=mesure_id, collection_name=name, **champs))
        await s.commit()


async def lister_resultats(name: str, mesure_id: str, *, verdict: str | None = None, page: int = 1, par_page: int = 50) -> PageResultats:
    par_page = max(1, min(int(par_page), 200))
    f = [MesureResultat.collection_name == name, MesureResultat.mesure_id == mesure_id]
    if verdict:
        f.append(MesureResultat.verdict == verdict)
    async with async_session() as s:
        total = (await s.execute(select(func.count()).select_from(MesureResultat).where(*f))).scalar_one()
        pages = max(1, ceil(total / par_page))
        page = max(1, min(int(page), pages))
        r = await s.execute(
            select(MesureResultat).where(*f).order_by(MesureResultat.score.asc().nulls_first(), MesureResultat.cree_le).offset((page - 1) * par_page).limit(par_page)
        )
        return PageResultats(total=total, page=page, pages=pages, par_page=par_page, resultats=[ResultatFiche.depuis(x) for x in r.scalars().all()])


async def supprimer_mesure(name: str, ident: str) -> None:
    async with async_session() as s:
        m = await s.get(Mesure, ident)
        if not m or m.collection_name != name:
            raise Introuvable("Mesure introuvable")
        if m.etat in ACTIVES:
            raise Conflit("Une mesure en cours ne se supprime pas.")
        await s.execute(delete(MesureResultat).where(MesureResultat.mesure_id == ident))
        await s.delete(m)
        await s.commit()


async def tendance(name: str, n: int = 10) -> list[TendanceFiche]:
    """Les n dernières mesures terminées, dans l'ordre chronologique."""
    async with async_session() as s:
        r = await s.execute(select(Mesure).where(Mesure.collection_name == name, Mesure.etat == "termine").order_by(Mesure.cree_le.desc()).limit(n))
        return [TendanceFiche(id=m.id, cree_le=m.cree_le.isoformat(), score=m.score, nb_questions=m.nb_questions, methode=m.methode) for m in reversed(r.scalars().all())]


async def marquer_interrompues() -> int:
    async with async_session() as s:
        r = await s.execute(select(Mesure).where(Mesure.etat.in_(ACTIVES)))
        orphelines = r.scalars().all()
        for m in orphelines:
            m.etat, m.phase, m.termine_le = "erreur", "fini", utcnow()
            m.erreur = "Interrompue par un redémarrage du service : relancez la mesure."
        await s.commit()
        return len(orphelines)


async def resultat_de(name: str, mesure_id: str | None, question_id: str) -> ResultatVolet | None:
    """Le résultat d'une question dans une mesure (sa dernière, pour le volet)."""
    if not mesure_id:
        return None
    async with async_session() as s:
        r = await s.execute(select(MesureResultat).where(MesureResultat.collection_name == name, MesureResultat.mesure_id == mesure_id, MesureResultat.question_id == question_id))
        x = r.scalars().first()
        if not x:
            return None
        m = await s.get(Mesure, mesure_id)
        return ResultatVolet(**ResultatFiche.depuis(x).model_dump(), mesure_le=m.cree_le.isoformat() if m and m.cree_le else None)
