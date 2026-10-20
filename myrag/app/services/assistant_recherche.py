"""Chercher pour le compte d'un assistant : charger sa fiche, calculer ce que la personne lit,
planifier, exécuter, fusionner, journaliser. L'orchestration du harnais (`app/harnais/`, qui
reste pur) avec la base et les droits. Appelé par la recherche v1 (`?assistant=`) et par les
routes `plan` / `executer`."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass

from app.auth import CurrentUser
from app.harnais import journal, perimetre
from app.harnais.connecteurs.openrag import ConnecteurOpenRAG
from app.harnais.contrat import Appelant, Canal, CapaciteClient, Contexte, FicheAssistant, Plan, Resultat
from app.harnais.execution import Execution
from app.harnais.execution import executer as executer_plan
from app.harnais.fusion import fusionner
from app.harnais.interfaces import Connecteur, Planificateur
from app.harnais.plan.toutes_les_sources import ToutesLesSources
from app.services import assistant_droits, assistant_store


class AssistantIntrouvable(Exception):
    """Inconnu, jamais publié, ou hors de portée de la personne : le même refus, pour ne rien divulguer."""


@dataclass
class Charge:
    fiche: FicheAssistant
    version: int
    modifier: bool
    #: Les sources `collection` de la fiche que la personne lit (le périmètre).
    lisibles: list[str]
    #: Les fiches de collection de ces sources, pour les titres et les droits à afficher.
    collections: dict[str, dict | None]


async def charger(ident: str, user: CurrentUser, hash_: str, superadmin: bool, *, brouillon: bool = False) -> Charge:
    """La fiche servie à cette personne : le brouillon (la dernière version enregistrée) si elle
    peut le demander ET le modifier, sinon la version publiée."""
    ligne = await assistant_store.lire(ident)
    if ligne is None:
        raise AssistantIntrouvable(ident)
    courante = FicheAssistant.model_validate(ligne["fiche"])
    voir, modifier, cols = await assistant_droits.droits(courante, ligne.get("cree_par_hash"), user=user, hash_=hash_, superadmin=superadmin)
    if not voir:
        raise AssistantIntrouvable(ident)
    if brouillon and modifier:
        fiche, version = courante, ligne.get("version_publiee") or 1
    else:
        publiee = await assistant_store.version_publiee(ident)
        if publiee is None:
            raise AssistantIntrouvable(ident)
        version, fiche = publiee
        voir, _, cols = await assistant_droits.droits(fiche, ligne.get("cree_par_hash"), user=user, hash_=hash_, superadmin=superadmin)
        if not voir:
            raise AssistantIntrouvable(ident)
    lisibles = perimetre.sources_lisibles(fiche, cols, groupes=user.groups, sub=user.sub)
    return Charge(fiche=fiche, version=version, modifier=modifier, lisibles=lisibles, collections=cols)


def contexte(charge: Charge, canal: Canal, *, capacites_client: set[CapaciteClient] | None = None, top_k: int = 20) -> Contexte:
    return Contexte(canal=canal, capacites_client=capacites_client or set(), sources_lisibles=charge.lisibles, top_k=top_k)


async def planifier(charge: Charge, question: str, ctx: Contexte, planificateur: Planificateur | None = None) -> Plan:
    return await (planificateur or ToutesLesSources(charge.version)).plan(charge.fiche, question, ctx)


async def executer(
    charge: Charge,
    plan: Plan,
    user: CurrentUser,
    hash_: str,
    canal: Canal,
    *,
    top_k: int = 20,
    connecteurs: Mapping[str, Connecteur] | None = None,
) -> tuple[Resultat, Execution]:
    """Exécute `plan` pour cette personne : le plan est d'abord ramené à son périmètre (une étape
    hors droit ou hors fiche disparaît), les passages d'une source hors périmètre ne sortent
    jamais. Écrit le journal (sans texte)."""
    debut = time.monotonic()
    plan = perimetre.restreindre_plan(plan, charge.lisibles)
    if connecteurs is None:
        commun = ConnecteurOpenRAG(top_k=top_k)
        connecteurs = {s: commun for s in charge.lisibles}
    execution = await executer_plan(plan, connecteurs, Appelant(sub=user.sub, groupes=list(user.groups)))
    toujours = {s.id for s in charge.fiche.sources if s.regime == "toujours"}
    fusion = fusionner(execution.par_etape, {e.n: e.poids for e in plan.etapes}, toujours=toujours, limite=top_k)
    passages = perimetre.restreindre_passages(fusion, charge.lisibles)
    plan_rendu = plan.model_copy(update={"sources_ignorees": plan.sources_ignorees + execution.sources_ignorees})
    duree_ms = int((time.monotonic() - debut) * 1000)
    par_source: dict[str, int] = {}
    for p in passages:
        par_source[p.source] = par_source.get(p.source, 0) + 1
    await journal.ecrire(journal.construire(plan, charge.fiche, execution, canal=canal, auteur_hash=hash_, duree_ms=duree_ms))
    return Resultat(plan=plan_rendu, passages=passages, duree_ms=duree_ms, par_source=par_source), execution
