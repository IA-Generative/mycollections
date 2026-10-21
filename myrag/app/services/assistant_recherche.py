"""Chercher pour le compte d'un assistant : charger sa fiche, calculer ce que la personne lit,
planifier, exécuter, fusionner, journaliser. L'orchestration du harnais (`app/harnais/`, qui
reste pur) avec la base et les droits. Appelé par la recherche v1 (`?assistant=`) et par les
routes `plan` / `executer`."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass

from app.auth import CurrentUser
from app.config import settings
from app.harnais import fiables, journal, perimetre
from app.harnais.apparieur import ApparieurEmbeddings, ApparieurSacDeMots
from app.harnais.connecteurs.eligibilite import ConnecteurEligibilite
from app.harnais.connecteurs.openrag import ConnecteurOpenRAG
from app.harnais.contrat import Appelant, Canal, CapaciteClient, Contexte, FicheAssistant, Plan, Resultat
from app.harnais.execution import Execution
from app.harnais.execution import executer as executer_plan
from app.harnais.fusion import fusionner
from app.harnais.interfaces import Apparieur, Connecteur, Planificateur
from app.harnais.plan.regles import Regles
from app.harnais.plan.toutes_les_sources import ToutesLesSources
from app.services import assistant_droits, assistant_store, connecteurs_declares, questions_store
from app.services.nommage import titre_de


class AssistantIntrouvable(Exception):
    """Inconnu, jamais publié, ou hors de portée de la personne : le même refus, pour ne rien divulguer."""


@dataclass
class Charge:
    fiche: FicheAssistant
    version: int
    modifier: bool
    #: Les sources de la fiche que la personne lit (le périmètre) : ses collections et les connecteurs déclarés.
    lisibles: list[str]
    #: Les fiches de collection de ces sources, pour les titres et les droits à afficher.
    collections: dict[str, dict | None]


async def charger(ident: str, user: CurrentUser, hash_: str, superadmin: bool, *, brouillon: bool = False) -> Charge:
    """La fiche servie à cette personne : le brouillon (la dernière version enregistrée) si elle
    peut le demander ET le modifier, sinon la version publiée."""
    ligne = await assistant_store.lire(ident)
    if ligne is None or ligne.get("archive_le"):
        raise AssistantIntrouvable(ident)  # un assistant archivé ne répond plus, à personne
    courante = FicheAssistant.model_validate(ligne["fiche"])
    voir, modifier, cols = await assistant_droits.droits(courante, ligne.get("cree_par_hash"), user=user, hash_=hash_, superadmin=superadmin)
    if brouillon and voir and modifier:
        fiche, version = courante, ligne.get("version_publiee") or 1
    else:
        # Qui ne gère pas le brouillon (ou ne le lit pas) a droit à la version publiée, s'il la lit.
        publiee = await assistant_store.version_publiee(ident)
        if publiee is None:
            raise AssistantIntrouvable(ident)
        version, fiche = publiee
        voir, _, cols = await assistant_droits.droits(fiche, ligne.get("cree_par_hash"), user=user, hash_=hash_, superadmin=superadmin)
        if not voir:
            raise AssistantIntrouvable(ident)
        modifier = False
    lisibles = perimetre.sources_lisibles(fiche, cols, groupes=user.groups, sub=user.sub, connecteurs=connecteurs_declares.lisibles_par(user.groups))
    return Charge(fiche=fiche, version=version, modifier=modifier, lisibles=lisibles, collections=cols)


def contexte(charge: Charge, canal: Canal, *, capacites_client: set[CapaciteClient] | None = None, top_k: int = 20) -> Contexte:
    return Contexte(canal=canal, capacites_client=capacites_client or set(), sources_lisibles=charge.lisibles, top_k=top_k)


def apparieur() -> Apparieur:
    """Les embeddings d'OpenRAG s'ils sont configurés (repli sur le sac de mots s'ils ne répondent pas), sinon le sac de mots."""
    if settings.assistants_embeddings_modele:
        return ApparieurEmbeddings(settings.openrag_url, settings.assistants_embeddings_modele, jeton=settings.openrag_admin_token, delai_s=settings.recherche_delai_s)
    return ApparieurSacDeMots()


def planificateur_regles(charge: Charge, app: Apparieur | None = None) -> Regles:
    """Le planificateur par règles, avec de quoi juger si une source `selon_question` ressemble à la question."""
    descriptions = {n: f"{titre_de(c)}. {c.get('description') or ''}".strip() for n, c in charge.collections.items() if c}
    for ident, d in connecteurs_declares.declarations().items():
        descriptions[ident] = " ".join([d.titre + ".", d.description, *d.exemples]).strip()
    return Regles(app or apparieur(), version=charge.version, descriptions=descriptions)


async def reponse_fiable(charge: Charge, question: str, app: Apparieur | None = None) -> fiables.Retenue | None:
    """La réponse fiable que cette question déclenche, parmi celles des seules sources que la personne lit."""
    lignes = await questions_store.reponses_fiables(charge.lisibles)
    candidats = [fiables.Candidat(id=q.id, question=q.question, reponse=q.reponse, source=q.collection_name) for q in lignes if q.reponse.strip()]
    return await fiables.choisir(question, candidats, app or apparieur(), charge.fiche.seuil_fiable)


async def planifier(charge: Charge, question: str, ctx: Contexte, planificateur: Planificateur | None = None, *, avec_fiables: bool = False, app: Apparieur | None = None) -> Plan:
    """Le plan de la recherche v1 (`?assistant=`) : toutes les sources lisibles. Les routes `plan` /
    `executer` passent `planificateur_regles(charge)` et `avec_fiables=True` : une réponse fiable
    reconnue donne un plan sans étape, qui dispense de toute recherche."""
    if avec_fiables:
        app = app or apparieur()
        retenue = await reponse_fiable(charge, question, app)
        if retenue is not None:
            nom = getattr(planificateur, "nom", "regles")
            return Plan(assistant=charge.fiche.assistant, version=charge.version, planificateur=nom, reponse_fiable=retenue.reference())
    return await (planificateur or ToutesLesSources(charge.version)).plan(charge.fiche, question, ctx)


class ReponseFiableInvalide(Exception):
    """Le plan cite une réponse fiable qui n'est pas (ou plus) servable à cette personne."""


async def servir_fiable(charge: Charge, plan: Plan, hash_: str, canal: Canal) -> Resultat:
    """Sert la réponse de référence citée par `plan.reponse_fiable`, sans aucune recherche. Elle est relue
    en base et doit être d'une source lisible, validée, fiable et pas hors sujet : un plan modifié par le
    client n'y change rien. Compte le service, écrit le journal (sans texte)."""
    debut = time.monotonic()
    q = await questions_store.lire_fiable(plan.reponse_fiable.id, charge.lisibles) if plan.reponse_fiable else None
    if q is None or not q.reponse.strip():
        raise ReponseFiableInvalide(plan.reponse_fiable.id if plan.reponse_fiable else "")
    plan = plan.model_copy(update={"etapes": []})
    await questions_store.marquer_servie(q.id)
    duree_ms = int((time.monotonic() - debut) * 1000)
    await journal.ecrire(journal.construire(plan, charge.fiche, Execution(sorties={}, duree_ms=duree_ms), canal=canal, auteur_hash=hash_, duree_ms=duree_ms))
    return Resultat(plan=plan, passages=[], reponse=q.reponse, duree_ms=duree_ms, par_source={})


def connecteurs_de(charge: Charge, *, top_k: int = 20) -> dict[str, Connecteur]:
    """Un connecteur par source lisible : OpenRAG (un seul, il groupe les requêtes) pour les
    collections, le sien pour un connecteur déclaré en configuration."""
    declares = connecteurs_declares.declarations()
    commun = ConnecteurOpenRAG(top_k=top_k)
    types = {s.id: s.type for s in charge.fiche.sources}
    rendu: dict[str, Connecteur] = {}
    for s in charge.lisibles:
        if types.get(s) == "connecteur":
            d = declares.get(s)
            if d is not None:
                rendu[s] = ConnecteurEligibilite(
                    ident=d.id, url=d.url, titre=d.titre, tables=d.tables, description=d.description, exemples=d.exemples, delai_s=settings.recherche_delai_s
                )
        else:
            rendu[s] = commun
    return rendu


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
    jamais. Écrit le journal (sans texte). Un plan à réponse fiable est servi sans recherche."""
    if plan.reponse_fiable is not None:
        return await servir_fiable(charge, plan, hash_, canal), Execution(sorties={}, duree_ms=0)
    debut = time.monotonic()
    plan = perimetre.restreindre_plan(plan, charge.lisibles)
    if connecteurs is None:
        connecteurs = connecteurs_de(charge, top_k=top_k)
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
