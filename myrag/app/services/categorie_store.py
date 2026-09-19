"""Les rubriques du catalogue : une collection en a une seule, ou aucune.

La liste, l'ordre et le classement se règlent à chaud par un superadmin
(app.routers.categories) ; rien ici ne contrôle l'accès.
"""

from __future__ import annotations

from sqlalchemy import func, select, update

from app.database import async_session
from app.models.db import Categorie, Collection
from app.services import journal

#: Semées au premier démarrage (database._semer_categories) : clé, libellé, description.
CATEGORIES_DE_DEPART = (
    ("droit-etrangers", "Droit des étrangers",
     "Séjour, asile, éloignement : textes, jurisprudence et doctrine."),
    ("securite-delinquance", "Sécurité et délinquance",
     "Infractions, statistiques de la délinquance, nomenclatures pénales."),
    ("securite-civile-routiere", "Sécurité civile et routière",
     "Secours, interventions, accidents de la circulation."),
    ("elus-vie-publique", "Élus et vie publique",
     "Élus, collectivités, vie démocratique locale."),
    ("textes-reference", "Textes juridiques de référence",
     "Codes et corpus officiels, toutes matières."),
    ("ressources-internes", "Ressources internes",
     "Règles de fonctionnement, achats, continuité, numérique."),
    ("guides-demonstrations", "Guides et démonstrations",
     "Modes d'emploi de Mes collections et corpus d'exemple."),
)


class Introuvable(Exception):
    pass


class DejaLa(Exception):
    pass


async def lister() -> list[dict]:
    """Les rubriques dans l'ordre d'affichage, avec le nombre de collections NON archivées."""
    async with async_session() as session:
        cats = (await session.execute(select(Categorie).order_by(Categorie.ordre, Categorie.libelle))).scalars().all()
        comptes = dict((await session.execute(
            select(Collection.categorie, func.count()).where(Collection.archived_at.is_(None))
            .group_by(Collection.categorie)
        )).all())
        return [{**c.to_dict(), "nb_collections": comptes.get(c.cle, 0)} for c in cats]


async def creer(cle: str, libelle: str, description: str = "") -> dict:
    async with async_session() as session:
        if await session.get(Categorie, cle):
            raise DejaLa(cle)
        dernier = (await session.execute(select(func.max(Categorie.ordre)))).scalar() or 0
        c = Categorie(cle=cle, libelle=libelle, description=description, ordre=dernier + 10)
        session.add(c)
        await session.commit()
        return c.to_dict()


async def modifier(cle: str, *, libelle: str | None = None, description: str | None = None) -> dict:
    async with async_session() as session:
        c = await session.get(Categorie, cle)
        if not c:
            raise Introuvable(cle)
        if libelle is not None:
            c.libelle = libelle
        if description is not None:
            c.description = description
        await session.commit()
        return c.to_dict()


async def supprimer(cle: str) -> int:
    """Retire la rubrique ; ses collections redeviennent « Non classées » dans la même
    transaction. Rend le nombre de collections déclassées."""
    async with async_session() as session:
        c = await session.get(Categorie, cle)
        if not c:
            raise Introuvable(cle)
        res = await session.execute(update(Collection).where(Collection.categorie == cle).values(categorie=None))
        await session.delete(c)
        await session.commit()
        return res.rowcount or 0


async def ordonner(cles: list[str]) -> list[dict]:
    """Pose l'ordre d'affichage. Les rubriques absentes de la liste passent après."""
    async with async_session() as session:
        cats = {c.cle: c for c in (await session.execute(select(Categorie))).scalars().all()}
        inconnues = [k for k in cles if k not in cats]
        if inconnues:
            raise Introuvable(", ".join(inconnues))
        for rang, cle in enumerate(cles, start=1):
            cats[cle].ordre = rang * 10
        reste = sorted((c for k, c in cats.items() if k not in cles), key=lambda c: (c.ordre, c.libelle))
        for rang, c in enumerate(reste, start=len(cles) + 1):
            c.ordre = rang * 10
        await session.commit()
    return await lister()


async def affecter(affectations: dict[str, str | None], auteur_hash: str) -> dict:
    """Classe des collections en lot. Chaque changement réel s'écrit au journal de la
    collection, dans la même transaction. Rend {changees, inchangees}."""
    async with async_session() as session:
        cles = {c.cle for c in (await session.execute(select(Categorie))).scalars().all()}
        mauvaises = sorted({v for v in affectations.values() if v is not None and v not in cles})
        if mauvaises:
            raise Introuvable("catégorie inconnue : " + ", ".join(mauvaises))
        changees, inchangees, absentes = [], [], []
        for name, cle in affectations.items():
            col = await session.get(Collection, name)
            if not col:
                absentes.append(name)
                continue
            if col.categorie == cle:
                inchangees.append(name)
                continue
            avant, col.categorie = col.categorie, cle
            journal.ecrire(session, "collection", name, "categorie.changee", auteur_hash=auteur_hash,
                           collection_name=name, detail={"avant": avant, "apres": cle})
            changees.append(name)
        if absentes:
            await session.rollback()
            raise Introuvable("collection inconnue : " + ", ".join(sorted(absentes)))
        await session.commit()
        return {"changees": changees, "inchangees": inchangees}
