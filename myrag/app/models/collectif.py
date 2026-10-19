"""Les fiches servies par le collectif : demandes, propositions, signalements, grille,
journal, amorces, suivi de la cloche.

Construites champ à champ depuis les attributs ORM (plus de `to_dict` sur les tables) :
ce que l'API sert est déclaré ici — ni `contact`, ni `recontact`, ni condensé d'auteur
(vie privée). Les dates sont servies en ISO 8601, comme avant.
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.db import Amorce, Demande, Evenement, GrilleControle, Proposition, Signalement


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _iso_vide(v: datetime | None) -> str:
    return v.isoformat() if v else ""


class DemandeFiche(BaseModel):
    """Une demande telle que servie : la table, plus ce que donnent les soutiens
    (nombre, garant, rôles) et le regard de l'appelant (soutenue, abonnée, sommeil)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    titre: str
    usage: str
    frequence: str
    service: str
    acces_actuel: str
    etat: str
    seuil: int
    amorce_id: str | None
    collection_name: str | None
    doublon_de: str | None
    motif_cloture: str | None
    satisfaction: str | None
    motif_insatisfaction: str | None
    confirmation_demandee_le: str | None
    cree_le: str
    maj_le: str
    nb_soutiens: int
    garant: bool
    roles: dict[str, int]
    temps_declare_min: int
    soutenue_par_moi: bool
    mon_role: str | None
    abonne: bool
    sommeil: bool
    seuil_atteint: bool
    je_suis_demandeur: bool
    confirmation_avant: str | None

    @classmethod
    def depuis(
        cls,
        d: Demande,
        *,
        nb_soutiens: int,
        garant: bool,
        roles: dict[str, int],
        temps_declare_min: int,
        soutenue_par_moi: bool,
        mon_role: str | None,
        abonne: bool,
        sommeil: bool,
        seuil_atteint: bool,
        je_suis_demandeur: bool,
        confirmation_avant: str | None,
    ) -> DemandeFiche:
        return cls(
            id=d.id,
            titre=d.titre,
            usage=d.usage,
            frequence=d.frequence,
            service=d.service or "",
            acces_actuel=d.acces_actuel,
            etat=d.etat,
            seuil=d.seuil,
            amorce_id=d.amorce_id,
            collection_name=d.collection_name,
            doublon_de=d.doublon_de,
            motif_cloture=d.motif_cloture,
            satisfaction=d.satisfaction,
            motif_insatisfaction=d.motif_insatisfaction,
            confirmation_demandee_le=_iso(d.confirmation_demandee_le),
            cree_le=_iso_vide(d.cree_le),
            maj_le=_iso_vide(d.maj_le),
            nb_soutiens=nb_soutiens,
            garant=garant,
            roles=roles,
            temps_declare_min=temps_declare_min,
            soutenue_par_moi=soutenue_par_moi,
            mon_role=mon_role,
            abonne=abonne,
            sommeil=sommeil,
            seuil_atteint=seuil_atteint,
            je_suis_demandeur=je_suis_demandeur,
            confirmation_avant=confirmation_avant,
        )


class DemandeLue(DemandeFiche):
    """Une demande lue par son garant ou l'administration : le courriel de l'auteur en plus."""

    contact_auteur: str | None = None


class DemandeSuivie(BaseModel):
    """Ce que la cloche affiche d'une demande : le projet de la fiche, sans le détail."""

    model_config = ConfigDict(extra="forbid")

    id: str
    titre: str
    etat: str
    nb_soutiens: int
    seuil: int
    garant: bool
    sommeil: bool
    soutenue_par_moi: bool
    mon_role: str | None
    collection_name: str | None
    je_suis_demandeur: bool
    confirmation_avant: str | None

    @classmethod
    def depuis_fiche(cls, d: DemandeFiche) -> DemandeSuivie:
        cles = {
            "id",
            "titre",
            "etat",
            "nb_soutiens",
            "seuil",
            "garant",
            "sommeil",
            "soutenue_par_moi",
            "mon_role",
            "collection_name",
            "je_suis_demandeur",
            "confirmation_avant",
        }
        return cls(**d.model_dump(include=cles))


class DoublonCandidat(DemandeFiche):
    """Une demande proche d'un titre déposé, avec sa similarité (0 à 1)."""

    similarite: float


class FicheCollection(BaseModel):
    """La fiche brute d'une collection, garant compris — jamais servie telle quelle."""

    model_config = ConfigDict(extra="forbid")

    name: str
    etat_collab: str
    garant_hash: str | None
    demande_id: str | None
    scope: str
    created_by: str
    scope_groups: list[str]
    archived_at: datetime | None


class EtatCollection(BaseModel):
    """L'état collaboratif d'une collection, et ce qu'on peut en faire."""

    model_config = ConfigDict(extra="forbid")

    collection: str
    etat: str
    etats: list[str]
    mention: str | None
    garant: bool
    garant_pressenti: str
    je_suis_garant: bool
    transitions_possibles: list[str]
    grille_complete: bool


class GrilleFiche(BaseModel):
    """La grille de contrôle d'une collection, servie même vide (jamais 404)."""

    model_config = ConfigDict(extra="forbid")

    collection: str
    source_licence: str
    donnees_perso: str
    fraicheur: str
    relecture_n: int
    relecteurs: int
    couverture: dict
    maj_le: str | None

    @classmethod
    def depuis(cls, g: GrilleControle) -> GrilleFiche:
        return cls(
            collection=g.collection_name,
            source_licence=g.source_licence or "",
            donnees_perso=g.donnees_perso or "",
            fraicheur=g.fraicheur or "",
            relecture_n=g.relecture_n or 0,
            relecteurs=len(json.loads(g.relecteurs_json or "[]")),
            couverture=json.loads(g.couverture_json or "{}"),
            maj_le=_iso(g.maj_le),
        )


class GrilleLue(GrilleFiche):
    """La grille servie à l'écran : la fiche, et si elle est complète (app.services.etats)."""

    complete: bool


class PropositionFiche(BaseModel):
    """Une modification proposée : un avant, un après, une justification, une source."""

    model_config = ConfigDict(extra="forbid")

    id: str
    collection: str
    cible_type: str
    cible_ref: str
    avant: str
    apres: str
    justification: str
    source: str | None
    etat: str
    motif_refus: str | None
    decide_le: str | None
    cree_le: str

    @classmethod
    def depuis(cls, p: Proposition) -> PropositionFiche:
        return cls(
            id=p.id,
            collection=p.collection_name,
            cible_type=p.cible_type,
            cible_ref=p.cible_ref or "",
            avant=p.avant or "",
            apres=p.apres,
            justification=p.justification,
            source=p.source,
            etat=p.etat,
            motif_refus=p.motif_refus,
            decide_le=_iso(p.decide_le),
            cree_le=_iso_vide(p.cree_le),
        )


class SignalementFiche(BaseModel):
    """Un défaut signalé sur une collection ou sur l'un de ses fichiers."""

    model_config = ConfigDict(extra="forbid")

    id: str
    collection: str
    fichier_id: int | None
    motif: str
    texte: str
    etat: str
    traite_le: str | None
    cree_le: str

    @classmethod
    def depuis(cls, s: Signalement) -> SignalementFiche:
        return cls(
            id=s.id,
            collection=s.collection_name,
            fichier_id=s.fichier_id,
            motif=s.motif,
            texte=s.texte,
            etat=s.etat,
            traite_le=_iso(s.traite_le),
            cree_le=_iso_vide(s.cree_le),
        )


class EvenementFiche(BaseModel):
    """Une ligne du fil d'avancement, signée d'une personne (condensé) ou d'un robot."""

    model_config = ConfigDict(extra="forbid")

    id: str
    objet_type: str
    objet_id: str
    collection: str | None
    type: str
    par: str
    detail: dict
    cree_le: str

    @classmethod
    def depuis(cls, e: Evenement) -> EvenementFiche:
        return cls(
            id=e.id,
            objet_type=e.objet_type,
            objet_id=e.objet_id,
            collection=e.collection_name,
            type=e.type,
            par=f"robot:{e.robot}" if e.robot else "personne",
            detail=json.loads(e.detail_json or "{}"),
            cree_le=_iso_vide(e.cree_le),
        )


class JournalPage(BaseModel):
    """Une page du fil d'avancement d'un objet, et la suite s'il y en a une."""

    model_config = ConfigDict(extra="forbid")

    evenements: list[EvenementFiche]
    suivant: str | None


class PropositionLue(BaseModel):
    """Une proposition et son historique de décisions."""

    model_config = ConfigDict(extra="forbid")

    proposition: PropositionFiche
    historique: list[EvenementFiche]


class AmorceEtat(BaseModel):
    """L'état d'import d'une amorce du catalogue (app/amorces/catalogue.json)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    collection_name: str | None
    etat_import: str
    dernier_import_le: str | None
    detail: dict
    erreur: str | None

    @classmethod
    def depuis(cls, a: Amorce) -> AmorceEtat:
        return cls(
            id=a.id,
            collection_name=a.collection_name,
            etat_import=a.etat_import,
            dernier_import_le=_iso(a.dernier_import_le),
            detail=json.loads(a.detail_json or "{}"),
            erreur=a.erreur,
        )


class ApplicationProposition(BaseModel):
    """Ce que donne l'application matérielle d'une proposition (lot 2)."""

    model_config = ConfigDict(extra="forbid")

    appliquee: bool
    motif: str


class Suivi(BaseModel):
    """Ce que la cloche montre à une personne : ses demandes, celles qui approchent
    du seuil, les collections qu'elle suit."""

    model_config = ConfigDict(extra="forbid")

    demandes: list[DemandeSuivie]
    presque_au_seuil: list[DemandeSuivie]
    collections: list[str]


class SuiviBus(Suivi):
    """Le suivi tel que la barre commune le sert : seuil et adresse en plus."""

    seuil_chantier: int
    url: str


class CollectionPublique(BaseModel):
    """Une collection publiée, telle que la liste publique la montre."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
