"""Accès en base de la génération : personas, runs, paires (docs/generation.md).

Chaque fonction ouvre sa session (patron de collectif_store). Les identités ne sont gardées
qu'en condensé (`signature`), jamais en clair.
"""

from __future__ import annotations

import json
from math import ceil

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models.db import Generation, PaireQA, Persona, utcnow
from app.services.collectif_store import Conflit, Introuvable, signature

ACTIFS = ("en_attente", "en_cours")


def condense(sub: str | None) -> str | None:
    return signature(sub).get("auteur_hash")


# ─── Personas ─────────────────────────────────────────────────────────────────────

async def lister_personas(name: str) -> list[dict]:
    async with async_session() as s:
        r = await s.execute(select(Persona).where(Persona.collection_name == name).order_by(Persona.cree_le))
        return [p.to_dict() for p in r.scalars().all()]


async def personas_par_ids(name: str, ids: list[str]) -> list[dict]:
    """Les personas demandés, dans l'ordre demandé ; Introuvable si l'un n'est pas de la collection."""
    async with async_session() as s:
        r = await s.execute(select(Persona).where(Persona.collection_name == name, Persona.id.in_(ids)))
        trouves = {p.id: p.to_dict() for p in r.scalars().all()}
    manquants = [i for i in ids if i not in trouves]
    if manquants:
        raise Introuvable(f"Persona inconnu dans cette collection : {', '.join(manquants)}")
    return [trouves[i] for i in ids]


async def creer_persona(name: str, nom: str, description_role: str, sub: str | None) -> dict:
    async with async_session() as s:
        p = Persona(collection_name=name, nom=nom, description_role=description_role, cree_par_hash=condense(sub))
        s.add(p)
        try:
            await s.commit()
        except IntegrityError:
            raise Conflit(f"Un persona s'appelle déjà « {nom} » dans cette collection")
        await s.refresh(p)
        return p.to_dict()


async def modifier_persona(name: str, ident: str, champs: dict) -> dict:
    async with async_session() as s:
        p = await s.get(Persona, ident)
        if not p or p.collection_name != name:
            raise Introuvable("Persona introuvable")
        for k in ("nom", "description_role"):
            if champs.get(k) is not None:
                setattr(p, k, champs[k])
        try:
            await s.commit()
        except IntegrityError:
            raise Conflit(f"Un persona s'appelle déjà « {champs.get('nom')} » dans cette collection")
        await s.refresh(p)
        return p.to_dict()


async def supprimer_persona(name: str, ident: str) -> None:
    async with async_session() as s:
        p = await s.get(Persona, ident)
        if not p or p.collection_name != name:
            raise Introuvable("Persona introuvable")
        await s.delete(p)
        await s.commit()


# ─── Runs ─────────────────────────────────────────────────────────────────────────

async def run_actif(name: str) -> dict | None:
    async with async_session() as s:
        r = await s.execute(select(Generation).where(Generation.collection_name == name, Generation.etat.in_(ACTIFS)))
        g = r.scalars().first()
        return g.to_dict() if g else None


async def creer_run(name: str, personas: list[dict], taille: int, distribution: dict, modele: str, sub: str | None) -> dict:
    if await run_actif(name):
        raise Conflit("Une génération est déjà en cours pour cette collection")
    async with async_session() as s:
        g = Generation(collection_name=name, taille=taille, modele=modele, lance_par_hash=condense(sub),
                       personas_json=json.dumps([{"id": p["id"], "nom": p["nom"]} for p in personas], ensure_ascii=False),
                       distribution_json=json.dumps(distribution))
        s.add(g)
        await s.commit()
        await s.refresh(g)
        return g.to_dict()


async def lister_runs(name: str, limite: int = 50) -> list[dict]:
    async with async_session() as s:
        r = await s.execute(select(Generation).where(Generation.collection_name == name)
                            .order_by(Generation.cree_le.desc()).limit(limite))
        return [g.to_dict() for g in r.scalars().all()]


async def lire_run(name: str, ident: str) -> dict:
    async with async_session() as s:
        g = await s.get(Generation, ident)
        if not g or g.collection_name != name:
            raise Introuvable("Génération introuvable")
        return g.to_dict()


async def maj_run(ident: str, **champs) -> None:
    async with async_session() as s:
        g = await s.get(Generation, ident)
        if not g:
            return
        for k, v in champs.items():
            if hasattr(g, k):
                setattr(g, k, v)
        await s.commit()


async def terminer_run(ident: str, etat: str, *, erreur: str | None = None, **champs) -> dict | None:
    async with async_session() as s:
        g = await s.get(Generation, ident)
        if not g:
            return None
        for k, v in champs.items():
            if hasattr(g, k) and v is not None:
                setattr(g, k, v)
        g.etat, g.phase, g.termine_le = etat, "fini", utcnow()
        g.erreur = erreur if etat == "erreur" else None
        if etat == "erreur" and not g.erreur:
            g.erreur = "Échec sans message"
        await s.commit()
        await s.refresh(g)
        return g.to_dict()


async def supprimer_run(name: str, ident: str) -> None:
    async with async_session() as s:
        g = await s.get(Generation, ident)
        if not g or g.collection_name != name:
            raise Introuvable("Génération introuvable")
        if g.etat in ACTIFS:
            raise Conflit("Une génération en cours ne se supprime pas")
        await s.execute(delete(PaireQA).where(PaireQA.run_id == ident))
        await s.delete(g)
        await s.commit()


async def marquer_interrompus() -> int:
    """Au démarrage : un run resté actif a perdu son fil avec le processus précédent."""
    async with async_session() as s:
        r = await s.execute(select(Generation).where(Generation.etat.in_(ACTIFS)))
        orphelins = r.scalars().all()
        for g in orphelins:
            g.etat, g.phase, g.termine_le = "erreur", "fini", utcnow()
            g.erreur = "Interrompue par un redémarrage du service : relancez la génération."
        await s.commit()
        return len(orphelins)


# ─── Paires ───────────────────────────────────────────────────────────────────────

async def enregistrer_paires(ident: str, name: str, paires: list) -> int:
    async with async_session() as s:
        for rang, p in enumerate(paires):
            s.add(PaireQA(run_id=ident, collection_name=name, rang=rang, question=p.question, reponse=p.reponse,
                          contextes_json=json.dumps(p.contextes, ensure_ascii=False), persona_nom=p.persona_nom,
                          synthetiseur=p.synthetiseur, style=p.style, longueur=p.longueur))
        await s.commit()
    return len(paires)


def _filtres(name: str, run_id: str, persona: str | None, relecture: str | None) -> list:
    f = [PaireQA.collection_name == name, PaireQA.run_id == run_id]
    if persona:
        f.append(PaireQA.persona_nom == persona)
    if relecture:
        f.append(PaireQA.relecture == relecture)
    return f


async def lister_paires(name: str, run_id: str, *, persona: str | None = None, relecture: str | None = None,
                        page: int = 1, par_page: int = 50) -> dict:
    par_page = max(1, min(int(par_page), 200))
    filtres = _filtres(name, run_id, persona, relecture)
    async with async_session() as s:
        total = (await s.execute(select(func.count()).select_from(PaireQA).where(*filtres))).scalar_one()
        pages = max(1, ceil(total / par_page))
        page = max(1, min(int(page), pages))
        r = await s.execute(select(PaireQA).where(*filtres).order_by(PaireQA.rang)
                            .offset((page - 1) * par_page).limit(par_page))
        return {"total": total, "page": page, "pages": pages, "par_page": par_page,
                "paires": [p.to_dict() for p in r.scalars().all()]}


async def paires_pour_export(name: str, run_id: str) -> list[dict]:
    async with async_session() as s:
        r = await s.execute(select(PaireQA).where(*_filtres(name, run_id, None, None)).order_by(PaireQA.rang))
        return [p.to_dict() for p in r.scalars().all()]


async def relire_paire(name: str, ident: str, relecture: str, commentaire: str | None, sub: str | None) -> dict:
    async with async_session() as s:
        p = await s.get(PaireQA, ident)
        if not p or p.collection_name != name:
            raise Introuvable("Paire introuvable")
        p.relecture = relecture
        if commentaire is not None:
            p.commentaire = commentaire
        p.relu_le = utcnow() if relecture != "brut" else None
        p.relu_par_hash = condense(sub) if relecture != "brut" else None
        await s.commit()
        await s.refresh(p)
        return p.to_dict()
