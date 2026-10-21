"""Le périmètre lisible : ce qu'un assistant a le droit de chercher pour CETTE personne.

La règle est celle de `access.can_read`, la même que les collections lisibles de la recherche v1
(`routers/recherche.py`) : une collection archivée ou inconnue n'est pas lisible. Une source hors
droit est ignorée et comptée, jamais nommée ni citée. Module pur : les fiches de collection sont
passées par l'appelant (le harnais ne lit pas la base)."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence

from app.harnais.contrat import Etape, FicheAssistant, Passage, Plan
from app.services import access


def collection_lisible(col: Mapping | None, *, groupes: Sequence[str] | None, sub: str | None) -> bool:
    if not col or col.get("archived_at"):
        return False
    return access.can_read(
        name=col["name"],
        scope=col.get("scope"),
        scope_groups=col.get("scope_groups"),
        created_by=col.get("created_by"),
        user_groups=list(groupes or []),
        user_sub=sub,
    )


def sources_lisibles(
    fiche: FicheAssistant,
    collections: Mapping[str, Mapping | None],
    *,
    groupes: Sequence[str] | None,
    sub: str | None,
    connecteurs: Collection[str] = (),
) -> list[str]:
    """Les sources de la fiche que la personne lit, par rang. Une source `collection` suit
    les droits de la collection. Une source `connecteur` est lisible si, et seulement si, elle est
    déclarée en configuration (`connecteurs`) : le référentiel n'a pas de droits propres, il est
    ouvert à toute personne qui passe la garde de l'application."""
    return [
        s.id
        for s in fiche.sources_ordonnees()
        if (s.type == "collection" and collection_lisible(collections.get(s.id), groupes=groupes, sub=sub)) or (s.type == "connecteur" and s.id in connecteurs)
    ]


def restreindre_plan(plan: Plan, lisibles: Iterable[str]) -> Plan:
    """Le plan sans les étapes dont la source n'est pas lisible. Les numéros restent ; les
    étapes qui attendaient une étape retirée ne l'attendent plus (et perdent leur `avec`)."""
    permis = set(lisibles)
    gardees = [e for e in plan.etapes if e.source in permis]
    retirees = {e.n for e in plan.etapes} - {e.n for e in gardees}
    nouvelles = []
    for e in gardees:
        attend = [a for a in e.attend if a not in retirees]
        nouvelles.append(Etape(n=e.n, source=e.source, question=e.question, poids=e.poids, attend=attend, avec=e.avec if attend else None))
    ignorees = len({e.source for e in plan.etapes if e.source not in permis})
    return plan.model_copy(update={"etapes": nouvelles, "sources_ignorees": plan.sources_ignorees + ignorees})


def restreindre_passages(passages: Iterable[Passage], lisibles: Iterable[str]) -> list[Passage]:
    """Dernier filet : aucun passage d'une source hors périmètre ne sort, quoi qu'ait rendu un connecteur."""
    permis = set(lisibles)
    return [p for p in passages if p.source in permis]
