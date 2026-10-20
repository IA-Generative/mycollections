"""Le réseau d'entraide : appels, réponses, liens vers les demandes. Toute décision d'état se
prend ICI, dans la transaction qui écrit ; aucune route n'accepte un état en entrée. Les demandes
du collectif sont lues en référence (`collectif_store`), jamais copiées."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select

from app.database import async_session
from app.models.db import Demande
from app.models.entraide import EntraideAppel, EntraideLien, EntraideReponse, maintenant
from app.services import collectif_store

PREFIXE_DEMANDE = "demande:"


class Introuvable(Exception): ...


class Conflit(Exception): ...


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def appel_vers_dict(a: EntraideAppel, moi_hash: str, *, nb_reponses: int = 0) -> dict:
    """Un appel tel que servi : jamais le condensé de l'auteur, seulement « est-ce le mien »."""
    return {
        "id": a.id,
        "type": a.type,
        "titre": a.titre,
        "texte": a.texte,
        "etat": a.etat,
        "demande_id": a.demande_id,
        "par_reference": False,
        "est_mon_appel": a.auteur_hash == moi_hash,
        "nb_reponses": nb_reponses,
        "cree_le": _iso(a.cree_le),
        "maj_le": _iso(a.maj_le),
        "publie_le": _iso(a.publie_le),
    }


def demande_vers_appel(d) -> dict:
    """Une demande du collectif vue comme un appel de type « donnée » — par référence."""
    return {
        "id": PREFIXE_DEMANDE + d.id,
        "type": "donnee",
        "titre": d.titre,
        "texte": d.usage,
        "etat": "clos" if d.etat in ("close", "realisee") else "publie",
        "etat_demande": d.etat,
        "demande_id": d.id,
        "par_reference": True,
        "est_mon_appel": False,
        "nb_reponses": d.nb_soutiens,
        "cree_le": d.cree_le,
        "maj_le": d.maj_le,
        "publie_le": d.cree_le,
    }


async def _nb_reponses(session, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    lignes = (await session.execute(select(EntraideReponse.appel_id, func.count()).where(EntraideReponse.appel_id.in_(ids)).group_by(EntraideReponse.appel_id))).all()
    return {i: n for i, n in lignes}


async def lister(moi_hash: str, *, type_: str | None = None, etat: str | None = None, q: str | None = None) -> list[dict]:
    """Les appels publiés ou clos, et mes brouillons ; les demandes en référence. Du plus récent."""
    sortie: list[dict] = []
    if type_ != "cherche" and type_ != "propose":
        for d in await collectif_store.lister_demandes(moi_hash):
            sortie.append(demande_vers_appel(d))
    if type_ in (None, "cherche", "propose"):
        async with async_session() as session:
            stmt = select(EntraideAppel).where(or_(EntraideAppel.etat != "brouillon", EntraideAppel.auteur_hash == moi_hash))
            if type_:
                stmt = stmt.where(EntraideAppel.type == type_)
            appels = (await session.execute(stmt)).scalars().all()
            nombres = await _nb_reponses(session, [a.id for a in appels])
            sortie.extend(appel_vers_dict(a, moi_hash, nb_reponses=nombres.get(a.id, 0)) for a in appels)
    if etat:
        sortie = [a for a in sortie if a["etat"] == etat]
    if q and q.strip():
        mots = q.strip().lower().split()
        sortie = [a for a in sortie if all(m in f"{a['titre']} {a['texte']}".lower() for m in mots)]
    sortie.sort(key=lambda a: a["maj_le"] or "", reverse=True)
    return sortie


async def _appel(session, ident: str) -> EntraideAppel:
    a = await session.get(EntraideAppel, ident)
    if not a:
        raise Introuvable(ident)
    return a


async def lire(ident: str, moi_hash: str) -> dict:
    """L'appel, ses réponses et ses demandes liées ; le brouillon d'une autre personne est introuvable."""
    if ident.startswith(PREFIXE_DEMANDE):
        try:
            d = await collectif_store.lire_demande(ident[len(PREFIXE_DEMANDE) :], moi_hash)
        except collectif_store.Introuvable:
            raise Introuvable(ident)
        return {**demande_vers_appel(d), "reponses": [], "demandes_liees": []}
    async with async_session() as session:
        a = await _appel(session, ident)
        if a.etat == "brouillon" and a.auteur_hash != moi_hash:
            raise Introuvable(ident)
        reponses = (await session.execute(select(EntraideReponse).where(EntraideReponse.appel_id == ident).order_by(EntraideReponse.cree_le))).scalars().all()
        liens = (await session.execute(select(EntraideLien.demande_id).where(EntraideLien.appel_id == ident))).scalars().all()
        d = appel_vers_dict(a, moi_hash, nb_reponses=len(reponses))
        d["reponses"] = [{"id": r.id, "texte": r.texte, "de_moi": r.auteur_hash == moi_hash, "cree_le": _iso(r.cree_le)} for r in reponses]
        d["demandes_liees"] = list(liens)
        return d


async def auteur_de(ident: str) -> str:
    async with async_session() as session:
        return (await _appel(session, ident)).auteur_hash


async def creer(entree: dict, moi_hash: str) -> dict:
    async with async_session() as session:
        a = EntraideAppel(type=entree["type"], titre=entree["titre"], texte=entree["texte"], etat="brouillon", auteur_hash=moi_hash)
        session.add(a)
        await session.commit()
        return appel_vers_dict(a, moi_hash)


async def publier(ident: str, moi_hash: str) -> dict:
    async with async_session() as session:
        a = await _appel(session, ident)
        if a.etat != "brouillon":
            raise Conflit("Cet appel est déjà publié")
        a.etat, a.publie_le = "publie", maintenant()
        await session.commit()
        return appel_vers_dict(a, moi_hash)


async def clore(ident: str, moi_hash: str) -> dict:
    async with async_session() as session:
        a = await _appel(session, ident)
        if a.etat == "clos":
            raise Conflit("Cet appel est déjà clos")
        a.etat, a.clos_le = "clos", maintenant()
        await session.commit()
        return appel_vers_dict(a, moi_hash)


async def repondre(ident: str, texte: str, moi_hash: str) -> dict:
    async with async_session() as session:
        a = await _appel(session, ident)
        if a.etat == "brouillon" and a.auteur_hash != moi_hash:
            raise Introuvable(ident)
        if a.etat != "publie":
            raise Conflit("On ne répond qu'à un appel publié et encore ouvert")
        r = EntraideReponse(appel_id=ident, texte=texte, auteur_hash=moi_hash)
        session.add(r)
        await session.commit()
        return {"id": r.id, "texte": r.texte, "de_moi": True, "cree_le": _iso(r.cree_le)}


async def lier_demande(ident: str, demande_id: str) -> list[str]:
    """Rattache l'appel à une demande existante (par référence, sans copie)."""
    async with async_session() as session:
        await _appel(session, ident)
        if not await session.get(Demande, demande_id):
            raise Introuvable(demande_id)
        if not await session.get(EntraideLien, (ident, demande_id)):
            session.add(EntraideLien(appel_id=ident, demande_id=demande_id))
            await session.commit()
        return list((await session.execute(select(EntraideLien.demande_id).where(EntraideLien.appel_id == ident))).scalars().all())
