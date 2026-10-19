"""Le magasin des assistants de recherche (ADR-0003) : le brouillon (`assistants` + `consignes`),
les versions immuables (`assistant_versions`) et le miroir d'une collection publiée. Tout ce qui
ÉCRIT un assistant passe par ici ; le harnais (lot A) ne fait que lire une version."""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError
from sqlalchemy import delete, select

from app.database import async_session
from app.harnais.contrat import IDENT_ASSISTANT, QUAND_TOUJOURS, Canaux, Consigne, FicheAssistant, Source, canonique, empreinte
from app.models.db import Assistant, AssistantVersion, Collection, ConsigneAssistant, PlanJournal, Publication, utcnow
from app.services import journal
from app.services.nommage import titre_de

logger = logging.getLogger("myrag.assistants")

ROBOT_MIGRATION = "migration:collections"
CONSIGNE_DEFAUT = "defaut"


class Introuvable(Exception):
    pass


# ─── Lecture ─────────────────────────────────────────────────────────────────────────────────


def _ligne_vers_consigne(ligne: ConsigneAssistant) -> Consigne:
    return Consigne(
        id=ligne.cle,
        quand=ligne.quand,
        exemples=json.loads(ligne.exemples_json or "[]"),
        chercher=json.loads(ligne.chercher_json or "[]"),
        repondre=ligne.repondre or "",
        gabarit=ligne.gabarit,
    )


async def _fiche_depuis(session, a: Assistant) -> FicheAssistant:
    lignes = (await session.execute(select(ConsigneAssistant).where(ConsigneAssistant.assistant_id == a.id).order_by(ConsigneAssistant.rang))).scalars().all()
    return FicheAssistant(
        assistant=a.id,
        titre=a.titre,
        rubrique=a.rubrique,
        description=a.description or "",
        sources=json.loads(a.sources_json or "[]"),
        consignes=[_ligne_vers_consigne(ligne) for ligne in lignes],
        seuil_fiable=float(a.seuil_fiable),
        validation_requise=bool(a.validation_requise),
        publication=Canaux.model_validate(json.loads(a.publication_json or "{}")),
    )


async def lire(ident: str) -> dict | None:
    """La ligne de l'assistant et son brouillon (`fiche`), ou None."""
    async with async_session() as s:
        a = await s.get(Assistant, ident)
        if a is None:
            return None
        d = a.to_dict()
        d["cree_par_hash"] = a.cree_par_hash  # pour les droits du routeur ; jamais rendu au client
        d["fiche"] = (await _fiche_depuis(s, a)).model_dump(mode="json")
        return d


async def lister(*, archives: bool = False) -> list[dict]:
    async with async_session() as s:
        q = select(Assistant).order_by(Assistant.titre, Assistant.id)
        if not archives:
            q = q.where(Assistant.archive_le.is_(None))
        return [a.to_dict() for a in (await s.execute(q)).scalars().all()]


async def fiche_brouillon(ident: str) -> FicheAssistant | None:
    async with async_session() as s:
        a = await s.get(Assistant, ident)
        return await _fiche_depuis(s, a) if a else None


async def version_publiee(ident: str) -> tuple[int, FicheAssistant] | None:
    """Le numéro et la fiche de la dernière version publiée, avec les canaux du brouillon."""
    async with async_session() as s:
        a = await s.get(Assistant, ident)
        if a is None or a.version_publiee is None:
            return None
        v = (await s.execute(select(AssistantVersion).where(AssistantVersion.assistant_id == ident, AssistantVersion.numero == a.version_publiee))).scalar_one_or_none()
        if v is None:
            return None
        return v.numero, FicheAssistant.depuis_canonique(v.contenu_json, Canaux.model_validate(json.loads(a.publication_json or "{}")))


async def versions(ident: str) -> list[dict]:
    async with async_session() as s:
        q = select(AssistantVersion).where(AssistantVersion.assistant_id == ident).order_by(AssistantVersion.numero)
        return [v.to_dict() for v in (await s.execute(q)).scalars().all()]


# ─── Écriture ────────────────────────────────────────────────────────────────────────────────


async def enregistrer_brouillon(fiche: FicheAssistant, *, auteur_hash: str | None = None, collection_name: str | None = None) -> dict:
    """Crée ou remplace le brouillon : la ligne `assistants` et TOUTES ses consignes."""
    async with async_session() as s:
        a = await s.get(Assistant, fiche.assistant)
        if a is None:
            a = Assistant(id=fiche.assistant, cree_par_hash=auteur_hash, collection_name=collection_name)
            s.add(a)
        a.titre = fiche.titre
        a.rubrique = fiche.rubrique
        a.description = fiche.description
        a.sources_json = json.dumps([src.model_dump(mode="json") for src in fiche.sources], ensure_ascii=False)
        a.publication_json = json.dumps(fiche.publication.model_dump(), ensure_ascii=False)
        a.validation_requise = fiche.validation_requise
        a.seuil_fiable = fiche.seuil_fiable
        a.maj_le = utcnow()
        await s.execute(delete(ConsigneAssistant).where(ConsigneAssistant.assistant_id == a.id))
        for rang, c in enumerate(fiche.consignes):
            s.add(
                ConsigneAssistant(
                    assistant_id=a.id,
                    cle=c.id,
                    rang=rang,
                    quand=c.quand,
                    exemples_json=json.dumps(c.exemples, ensure_ascii=False),
                    chercher_json=json.dumps([e.model_dump(mode="json") for e in c.chercher], ensure_ascii=False),
                    repondre=c.repondre,
                    gabarit=c.gabarit,
                )
            )
        await s.commit()
        return a.to_dict()


async def publier(ident: str, *, auteur_hash: str | None = None, robot: str | None = None) -> dict:
    """Fige le brouillon en version : une ligne de plus seulement si l'empreinte change (publier
    deux fois le même brouillon ne fait qu'une version). Signée d'une personne OU d'un robot."""
    if bool(auteur_hash) == bool(robot):
        raise ValueError("une publication est signée d'une personne OU d'un robot")
    async with async_session() as s:
        a = await s.get(Assistant, ident)
        if a is None:
            raise Introuvable(ident)
        fiche = await _fiche_depuis(s, a)
        texte = canonique(fiche)
        emp = empreinte(texte)
        derniere = (await s.execute(select(AssistantVersion).where(AssistantVersion.assistant_id == ident).order_by(AssistantVersion.numero.desc()).limit(1))).scalar_one_or_none()
        if derniere is not None and derniere.empreinte == emp:
            a.version_publiee = derniere.numero
            await s.commit()
            return {"assistant": ident, "version": derniere.numero, "empreinte": emp, "nouvelle": False}
        numero = (derniere.numero + 1) if derniere else 1
        s.add(AssistantVersion(assistant_id=ident, numero=numero, empreinte=emp, contenu_json=texte, publie_par_hash=auteur_hash, robot=robot))
        a.version_publiee = numero
        a.maj_le = utcnow()
        journal.ecrire(
            s, "assistant", ident, "assistant.publie", auteur_hash=auteur_hash, robot=robot, collection_name=a.collection_name, detail={"version": numero, "empreinte": emp}
        )
        await s.commit()
        return {"assistant": ident, "version": numero, "empreinte": emp, "nouvelle": True}


# ─── Le miroir d'une collection ──────────────────────────────────────────────────────────────


def deriver_identifiant(name: str) -> str:
    """L'identifiant d'assistant dérivé d'un nom de collection : le nom lui-même quand il est
    conforme (c'est le cas des noms que `nommage` accepte), sinon normalisé."""
    n = (name or "").strip().lower()
    if re.fullmatch(IDENT_ASSISTANT, n):
        return n
    n = re.sub(r"[^a-z0-9._-]+", "-", n).strip("._-")
    if len(n) < 3:
        n = f"{n}-assistant" if n else "assistant"
    return n[:64]


async def _identifiant_libre(session, name: str) -> str:
    base = deriver_identifiant(name)
    candidat, n = base, 1
    while True:
        a = await session.get(Assistant, candidat)
        if a is None or a.collection_name == name:
            return candidat
        n += 1
        candidat = f"{base[: 64 - len(str(n)) - 1]}-{n}"


def _fiche_miroir(ident: str, col: dict, pub: Publication) -> FicheAssistant:
    return FicheAssistant(
        assistant=ident,
        titre=titre_de(col)[:255],
        rubrique=col.get("categorie"),
        description=(col.get("description") or "")[:2000],
        sources=[Source(id=col["name"], type="collection", regime="toujours", rang=1)],
        consignes=[Consigne(id=CONSIGNE_DEFAUT, quand=QUAND_TOUJOURS, gabarit=col.get("prompt_template") or None, repondre=(col.get("system_prompt") or "")[:4000])],
        publication=Canaux(
            socle=bool(pub.alias_enabled or pub.tool_enabled),
            portail=True,
            fenetre_js=bool(pub.embed_enabled or pub.widget_enabled or pub.browser_enabled),
            api=True,
        ),
    )


async def assurer_miroir(name: str) -> str:
    """Une collection publiée (publication `published`, collection non archivée) a son assistant
    à une source ; dépubliée ou archivée, son miroir est mis en sommeil, jamais effacé ; republiée,
    il se réveille. Idempotent : rend « cree », « inchange », « archive », « reactive »,
    « hors_critere » ou « invalide »."""
    async with async_session() as s:
        col = await s.get(Collection, name)
        pub = await s.get(Publication, name)
        publiee = col is not None and col.archived_at is None and pub is not None and pub.state == "published"
        existant = (await s.execute(select(Assistant).where(Assistant.collection_name == name))).scalar_one_or_none()
        if not publiee:
            if existant is not None and existant.archive_le is None:
                existant.archive_le = utcnow()
                journal.ecrire(s, "collection", name, "assistant.sommeil", robot=ROBOT_MIGRATION, collection_name=name, detail={"assistant": existant.id})
                await s.commit()
                return "archive"
            return "hors_critere"
        if existant is not None:
            if existant.archive_le is not None:
                existant.archive_le = None
                journal.ecrire(s, "collection", name, "assistant.reveil", robot=ROBOT_MIGRATION, collection_name=name, detail={"assistant": existant.id})
                await s.commit()
                return "reactive"
            return "inchange"
        ident = await _identifiant_libre(s, name)
        try:
            fiche = _fiche_miroir(ident, col.to_dict(), pub)
        except ValidationError as e:
            logger.warning("collection %s : pas d'assistant miroir (%s)", name, e.errors()[0].get("msg", "fiche invalide"))
            return "invalide"
    await enregistrer_brouillon(fiche, collection_name=name)
    await publier(ident, robot=ROBOT_MIGRATION)
    async with async_session() as s:
        journal.ecrire(s, "collection", name, "assistant.derive", robot=ROBOT_MIGRATION, collection_name=name, detail={"assistant": ident})
        await s.commit()
    return "cree"


async def purger_miroir(name: str) -> dict:
    """Efface l'assistant miroir d'une collection et tout ce qui s'y rattache (purge)."""
    async with async_session() as s:
        a = (await s.execute(select(Assistant).where(Assistant.collection_name == name))).scalar_one_or_none()
        if a is None:
            return {"assistants": 0}
        comptes: dict[str, int] = {}
        for modele in (AssistantVersion, ConsigneAssistant, PlanJournal):
            r = await s.execute(delete(modele).where(modele.assistant_id == a.id))
            comptes[modele.__tablename__] = r.rowcount or 0
        await s.delete(a)
        comptes["assistants"] = 1
        await s.commit()
        return comptes
