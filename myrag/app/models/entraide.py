"""Les tables du réseau d'entraide (lot G du chantier des assistants de recherche).

Le lot G y écrit ses tables `entraide_*` sans toucher `db.py`, qui importe ce module. Module
détachable : rien d'autre que `db.py` ne doit l'importer. Aucune donnée personnelle en clair :
les identités sont des condensés (`app/services/pseudo.py`), colonnes en `_hash`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: « donnée » : une demande du collectif, affichée par référence ; les deux autres s'écrivent ici.
TYPES_APPEL = ("donnee", "cherche", "propose")
#: Les types qu'une personne rédige dans le réseau (les demandes se déposent sur /api/demandes).
TYPES_REDIGES = ("cherche", "propose")
ETATS_APPEL = ("brouillon", "publie", "clos")


def maintenant() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naïf UTC, comme db.utcnow


def _id() -> str:
    return str(uuid.uuid4())


def _domaine(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({', '.join(repr(v) for v in valeurs)})"


class EntraideAppel(Base):
    """Un appel : brouillon, puis publié, puis clos. `demande_id` rattache un appel à une demande."""

    __tablename__ = "entraide_appel"
    __table_args__ = (
        CheckConstraint(_domaine("type", TYPES_APPEL), name="entraide_appel_type_valide"),
        CheckConstraint(_domaine("etat", ETATS_APPEL), name="entraide_appel_etat_valide"),
        Index("entraide_appel_etat", "etat", "maj_le"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    titre: Mapped[str] = mapped_column(String(200), nullable=False)
    texte: Mapped[str] = mapped_column(Text, nullable=False, default="")
    etat: Mapped[str] = mapped_column(String(20), nullable=False, default="brouillon")
    auteur_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    demande_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    # Un salon Tchap pour échanger : lien https validé (app/services/tchap.py), jamais une adresse de messagerie.
    lien_tchap: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    maj_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant, onupdate=maintenant)
    publie_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    clos_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class EntraideReponse(Base):
    """Une réponse à un appel publié."""

    __tablename__ = "entraide_reponse"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    appel_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    texte: Mapped[str] = mapped_column(Text, nullable=False)
    auteur_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)


class EntraideLien(Base):
    """Un appel qui renvoie à une demande du collectif (`demande.id`), lue en référence."""

    __tablename__ = "entraide_lien"

    appel_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    demande_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
