"""SQLAlchemy models for MyRAG persistent storage."""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow():
    # Return a naive UTC datetime. SQLAlchemy's DateTime column maps to
    # TIMESTAMP WITHOUT TIME ZONE on PostgreSQL; asyncpg rejects tz-aware
    # values against that type ("can't subtract offset-naive and offset-aware
    # datetimes"). Keeping everything naive-UTC avoids a schema migration.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def nouvel_id() -> str:
    """Identifiant portable (SQLite et PostgreSQL) pour les tables du collectif."""
    return str(uuid.uuid4())


# ─── Le circuit collaboratif d'une collection (ADR-0001) ─────────────────────────
# Une collection naît « amorcée », passe « en contrôle », est « publiée au groupe »,
# puis seulement « publiée à tous ». Tant qu'elle n'est pas publiée à tous, elle n'est
# servie qu'à son groupe et ses réponses portent la mention « en cours de vérification ».
# Le domaine est tenu par app.services.etats (SQLite ne sait pas ajouter une contrainte
# à une table existante) ; les tables neuves, elles, portent leurs CHECK.
ETATS_COLLECTION = ("amorcee", "en_controle", "publiee_groupe", "publiee_tous")


class Collection(Base):
    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Ce que lit une personne : « Codes NATINF ». `name` reste l'identifiant technique
    # (partition OpenRAG, modèle `openrag-<name>`, URL). Vide = repli sur le nom
    # (app.services.nommage.titre_de). La catégorie ne se pose que par
    # PUT /api/categories/affectations (superadmin) ; NULL = « Non classées ».
    titre: Mapped[str] = mapped_column(String(255), default="", server_default="")
    categorie: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    description: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(50), default="auto")
    sensitivity: Mapped[str] = mapped_column(String(50), default="public")
    prompt_template: Mapped[str] = mapped_column(String(100), default="generic")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    graph_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary_threshold: Mapped[int] = mapped_column(Integer, default=1000)
    scope: Mapped[str] = mapped_column(String(50), default="group")
    # Chemins de groupes Keycloak autorisés à interroger la collection quand
    # scope == "group" (liste JSON). Honoré par app.services.access.can_read.
    scope_groups_json: Mapped[str] = mapped_column(Text, default="[]")
    # sub Keycloak du créateur : lui garantit l'accès à sa propre collection
    # indépendamment du claim `groups` (qui ne se met à jour qu'au refresh token).
    created_by: Mapped[str] = mapped_column(String(255), default="", index=True)
    contact_name: Mapped[str] = mapped_column(String(255), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(50), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    # Circuit collaboratif. NULL sur les lignes antérieures, rétro-rempli au démarrage
    # (database._retro_remplir_etat_collab) d'après la publication ; « amorcee » à la
    # création. Le garant est un CONDENSÉ (HMAC du sub, app.services.pseudo), jamais le sub.
    etat_collab: Mapped[str | None] = mapped_column(String(30), nullable=True, default="amorcee")
    garant_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    garant_pressenti: Mapped[str] = mapped_column(String(255), default="", server_default="")
    demande_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "titre": self.titre or "",
            "categorie": self.categorie,
            "etat_collab": self.etat_collab,
            "garant": bool(self.garant_hash),
            "garant_pressenti": self.garant_pressenti or "",
            "demande_id": self.demande_id,
            "description": self.description,
            "strategy": self.strategy,
            "sensitivity": self.sensitivity,
            "prompt_template": self.prompt_template,
            "system_prompt": self.system_prompt,
            "graph_enabled": self.graph_enabled,
            "ai_summary_enabled": self.ai_summary_enabled,
            "ai_summary_threshold": self.ai_summary_threshold,
            "scope": self.scope,
            "scope_groups": json.loads(self.scope_groups_json or "[]"),
            "created_by": self.created_by,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }


class Categorie(Base):
    """Une rubrique du catalogue. Une collection en a une seule (collections.categorie)
    ou aucune ; la liste et l'ordre se règlent à chaud par un superadmin."""

    __tablename__ = "categories"

    cle: Mapped[str] = mapped_column(String(64), primary_key=True)
    libelle: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    ordre: Mapped[int] = mapped_column(Integer, default=0, index=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "cle": self.cle,
            "libelle": self.libelle,
            "description": self.description or "",
            "ordre": self.ordre or 0,
        }


class Publication(Base):
    __tablename__ = "publications"

    collection_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    state: Mapped[str] = mapped_column(String(50), default="draft")
    alias_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    alias_name: Mapped[str] = mapped_column(String(255), default="")
    # Saisie à la publication. Elle n'était PAS gardée : le champ revenait vide à chaque
    # ouverture de la page, et une republication l'effaçait de la fiche du modèle.
    alias_description: Mapped[str] = mapped_column(Text, default="", server_default="")
    tool_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    embed_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(50), default="group")
    visibility_groups_json: Mapped[str] = mapped_column(Text, default="[]")
    widget_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    browser_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str] = mapped_column(String(255), default="")

    def to_dict(self) -> dict:
        return {
            "collection": self.collection_name,
            "state": self.state,
            "alias_enabled": self.alias_enabled,
            "alias_name": self.alias_name,
            "alias_description": self.alias_description or "",
            "tool_enabled": self.tool_enabled,
            "embed_enabled": self.embed_enabled,
            "visibility": self.visibility,
            "visibility_groups": json.loads(self.visibility_groups_json or "[]"),
            "widget_enabled": self.widget_enabled,
            "browser_enabled": self.browser_enabled,
            "published_at": self.published_at.isoformat() if self.published_at else "",
            "published_by": self.published_by,
        }


class PublicationHistory(Base):
    __tablename__ = "publication_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(50))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    acted_by: Mapped[str] = mapped_column(String(255), default="")
    acted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    job_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str] = mapped_column(String(500), default="")
    source_path: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(50), default="auto")
    sensitivity: Mapped[str] = mapped_column(String(50), default="public")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_chunks: Mapped[int] = mapped_column(Integer, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def progress_pct(self) -> int:
        if self.total_chunks == 0:
            return 0
        return int(self.uploaded_chunks / self.total_chunks * 100)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "collection": self.collection_name,
            "filename": self.filename,
            "source_path": self.source_path,
            "strategy": self.strategy,
            "sensitivity": self.sensitivity,
            "status": self.status,
            "total_chunks": self.total_chunks,
            "uploaded_chunks": self.uploaded_chunks,
            "failed_chunks": self.failed_chunks,
            "progress_pct": self.progress_pct,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else "",
        }


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, default=0)  # -1, 0, 1
    reason: Mapped[str] = mapped_column(Text, default="")
    owui_chat_id: Mapped[str] = mapped_column(String(255), default="")
    owui_message_id: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    promoted_to: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "question": self.question,
            "response": self.response,
            "rating": self.rating,
            "reason": self.reason,
            "status": self.status,
            "promoted_to": self.promoted_to,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "name": self.name,
            "description": self.description,
            "questions": json.loads(self.questions_json or "[]"),
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer)
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "dataset_id": self.dataset_id,
            "results": json.loads(self.results_json or "[]"),
            "score": self.score,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class SourceFile(Base):
    """R7 — Stored source files for re-indexation."""
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    original_url: Mapped[str] = mapped_column(Text, default="")
    storage_path: Mapped[str] = mapped_column(Text)  # local path or S3 key
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(255), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")  # SHA-256
    strategy_used: Mapped[str] = mapped_column(String(50), default="auto")
    chunks_produced: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "filename": self.filename,
            "original_url": self.original_url,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "strategy_used": self.strategy_used,
            "chunks_produced": self.chunks_produced,
            "last_indexed_at": self.last_indexed_at.isoformat() if self.last_indexed_at else "",
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


# ═══════════════════════════════════════════════════════════════════════════════════
# Le collectif : demandes, soutiens, propositions, signalements, grille, journal.
# Aucun `sub` en clair dans ces tables : toute identité est un condensé HMAC salé
# (app.services.pseudo), le même que celui du bus de la bêta. Le courriel de recontact
# est la seule exception, ENCADRÉE : il n'existe que consenti (contrainte, pas politesse).
# ═══════════════════════════════════════════════════════════════════════════════════

FREQUENCES_DEMANDE = ("quotidienne", "hebdomadaire", "mensuelle", "ponctuelle")
ETATS_DEMANDE = ("ouverte", "chantier", "realisee", "close")
ROLES_SOUTIEN = ("soutien", "fournisseur", "relecteur", "garant")
OBJETS_ABONNEMENT = ("demande", "collection")
CIBLES_PROPOSITION = ("ligne", "fichier")
ETATS_PROPOSITION = ("proposee", "publiee", "refusee")
MOTIFS_SIGNALEMENT = ("obsolete", "erreur", "manquant")
ETATS_SIGNALEMENT = ("ouvert", "pris_en_compte", "clos")
OBJETS_EVENEMENT = ("demande", "collection", "proposition", "signalement", "synchronisation")
ETATS_IMPORT_AMORCE = ("jamais", "en_cours", "termine", "echec")


def _domaine(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({', '.join(repr(v) for v in valeurs)})"


class Demande(Base):
    """Un jeu de données qui manque : un usage et une fréquence, jamais un score."""

    __tablename__ = "demande"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nouvel_id)
    titre: Mapped[str] = mapped_column(String(200), nullable=False)
    usage: Mapped[str] = mapped_column(Text, nullable=False)
    frequence: Mapped[str] = mapped_column(String(20), nullable=False)
    service: Mapped[str] = mapped_column(String(120), default="")
    # Comment la personne se procure la donnée AUJOURD'HUI. Obligatoire : sans cette
    # information, constituer un nouveau jeu est pratiquement impossible.
    acces_actuel: Mapped[str] = mapped_column(Text, nullable=False)
    # Réponse EXPLICITE à « acceptez-vous d'être recontacté·e ? » — pas de défaut.
    recontact: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    etat: Mapped[str] = mapped_column(String(20), nullable=False, default="ouverte")
    # Le seuil en vigueur à la création, FIGÉ : changer capacites.json ne rejuge pas
    # les demandes passées.
    seuil: Mapped[int] = mapped_column(Integer, nullable=False)
    cree_par_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    amorce_id: Mapped[str | None] = mapped_column(String(60), nullable=True, default=None)
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    doublon_de: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    motif_cloture: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    maj_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint(_domaine("frequence", FREQUENCES_DEMANDE), name="demande_frequence_valide"),
        CheckConstraint(_domaine("etat", ETATS_DEMANDE), name="demande_etat_valide"),
        CheckConstraint(
            "etat <> 'close' OR doublon_de IS NOT NULL OR motif_cloture IS NOT NULL",
            name="demande_cloture_motivee",
        ),
        CheckConstraint("contact IS NULL OR recontact", name="demande_contact_consenti"),
        Index("demande_etat_maj", "etat", "maj_le"),
    )

    def to_dict(self) -> dict:
        # Ni `contact`, ni `recontact`, ni le condensé de l'auteur : ce que l'API sert
        # est lisible par tout le groupe ; le consentement, lui, se lit en base.
        return {
            "id": self.id,
            "titre": self.titre,
            "usage": self.usage,
            "frequence": self.frequence,
            "service": self.service or "",
            "acces_actuel": self.acces_actuel,
            "etat": self.etat,
            "seuil": self.seuil,
            "amorce_id": self.amorce_id,
            "collection_name": self.collection_name,
            "doublon_de": self.doublon_de,
            "motif_cloture": self.motif_cloture,
            "cree_le": self.cree_le.isoformat() if self.cree_le else "",
            "maj_le": self.maj_le.isoformat() if self.maj_le else "",
        }


class Soutien(Base):
    """Une personne derrière une demande, avec le rôle qu'elle prend et le temps qu'elle offre."""

    __tablename__ = "soutien"

    demande_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sub_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="soutien")
    temps_declare_min: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(_domaine("role", ROLES_SOUTIEN), name="soutien_role_valide"),
        CheckConstraint(
            "temps_declare_min IS NULL OR temps_declare_min BETWEEN 0 AND 100000",
            name="soutien_temps_borne",
        ),
    )


class Abonnement(Base):
    """Qui reçoit le fil d'avancement d'une demande ou d'une collection."""

    __tablename__ = "abonnement"

    objet_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    objet_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    sub_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(_domaine("objet_type", OBJETS_ABONNEMENT), name="abonnement_objet_valide"),
    )


class Proposition(Base):
    """Une modification proposée : un avant, un après, une justification, une source facultative."""

    __tablename__ = "proposition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nouvel_id)
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cible_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cible_ref: Mapped[str] = mapped_column(String(255), default="")
    avant: Mapped[str] = mapped_column(Text, default="")
    apres: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    auteur_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    etat: Mapped[str] = mapped_column(String(20), nullable=False, default="proposee")
    motif_refus: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    decide_par_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    decide_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(_domaine("cible_type", CIBLES_PROPOSITION), name="proposition_cible_valide"),
        CheckConstraint(_domaine("etat", ETATS_PROPOSITION), name="proposition_etat_valide"),
        CheckConstraint("etat <> 'refusee' OR motif_refus IS NOT NULL", name="proposition_refus_motive"),
        CheckConstraint("etat = 'proposee' OR decide_le IS NOT NULL", name="proposition_decision_datee"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "cible_type": self.cible_type,
            "cible_ref": self.cible_ref or "",
            "avant": self.avant or "",
            "apres": self.apres,
            "justification": self.justification,
            "source": self.source,
            "etat": self.etat,
            "motif_refus": self.motif_refus,
            "decide_le": self.decide_le.isoformat() if self.decide_le else None,
            "cree_le": self.cree_le.isoformat() if self.cree_le else "",
        }


class Signalement(Base):
    """Un défaut signalé sur une collection ou sur l'un de ses fichiers."""

    __tablename__ = "signalement"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nouvel_id)
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    fichier_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    motif: Mapped[str] = mapped_column(String(20), nullable=False)
    texte: Mapped[str] = mapped_column(Text, nullable=False)
    auteur_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    etat: Mapped[str] = mapped_column(String(20), nullable=False, default="ouvert")
    traite_par_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    traite_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(_domaine("motif", MOTIFS_SIGNALEMENT), name="signalement_motif_valide"),
        CheckConstraint(_domaine("etat", ETATS_SIGNALEMENT), name="signalement_etat_valide"),
        CheckConstraint("etat = 'ouvert' OR traite_le IS NOT NULL", name="signalement_traitement_date"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "fichier_id": self.fichier_id,
            "motif": self.motif,
            "texte": self.texte,
            "etat": self.etat,
            "traite_le": self.traite_le.isoformat() if self.traite_le else None,
            "cree_le": self.cree_le.isoformat() if self.cree_le else "",
        }


class GrilleControle(Base):
    """La grille de contrôle d'une collection — servie même vide, jamais 404."""

    __tablename__ = "grille_controle"

    collection_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_licence: Mapped[str] = mapped_column(Text, default="")
    donnees_perso: Mapped[str] = mapped_column(Text, default="")
    fraicheur: Mapped[str] = mapped_column(Text, default="")
    relecture_n: Mapped[int] = mapped_column(Integer, default=0)
    relecteurs_json: Mapped[str] = mapped_column(Text, default="[]")
    couverture_json: Mapped[str] = mapped_column(Text, default="{}")
    maj_par_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    maj_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    def to_dict(self) -> dict:
        return {
            "collection": self.collection_name,
            "source_licence": self.source_licence or "",
            "donnees_perso": self.donnees_perso or "",
            "fraicheur": self.fraicheur or "",
            "relecture_n": self.relecture_n or 0,
            "relecteurs": len(json.loads(self.relecteurs_json or "[]")),
            "couverture": json.loads(self.couverture_json or "{}"),
            "maj_le": self.maj_le.isoformat() if self.maj_le else None,
        }


class Evenement(Base):
    """Le fil d'avancement : une ligne par geste, signée d'une personne OU d'un robot."""

    __tablename__ = "evenement"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nouvel_id)
    objet_type: Mapped[str] = mapped_column(String(20), nullable=False)
    objet_id: Mapped[str] = mapped_column(String(255), nullable=False)
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    auteur_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    robot: Mapped[str | None] = mapped_column(String(60), nullable=True, default=None)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(_domaine("objet_type", OBJETS_EVENEMENT), name="evenement_objet_valide"),
        CheckConstraint(
            "(auteur_hash IS NULL) <> (robot IS NULL)",
            name="evenement_auteur_ou_robot",
        ),
        Index("evenement_objet_date", "objet_type", "objet_id", "cree_le"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "objet_type": self.objet_type,
            "objet_id": self.objet_id,
            "collection": self.collection_name,
            "type": self.type,
            "par": f"robot:{self.robot}" if self.robot else "personne",
            "detail": json.loads(self.detail_json or "{}"),
            "cree_le": self.cree_le.isoformat() if self.cree_le else "",
        }


class Amorce(Base):
    """L'état d'import d'une amorce du catalogue (app/amorces/catalogue.json)."""

    __tablename__ = "amorce"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    etat_import: Mapped[str] = mapped_column(String(20), nullable=False, default="jamais")
    dernier_import_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    erreur: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    __table_args__ = (
        CheckConstraint(_domaine("etat_import", ETATS_IMPORT_AMORCE), name="amorce_etat_import_valide"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection_name": self.collection_name,
            "etat_import": self.etat_import,
            "dernier_import_le": self.dernier_import_le.isoformat() if self.dernier_import_le else None,
            "detail": json.loads(self.detail_json or "{}"),
            "erreur": self.erreur,
        }
