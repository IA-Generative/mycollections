"""Les connecteurs déclarés par configuration (`MYCOLLECTIONS_CONNECTEURS`, un tableau JSON).

Une déclaration illisible, d'un type inconnu ou en double est ignorée (et journalisée sans son
contenu) : une faute de frappe dans la configuration n'éteint pas l'application. Rien n'est
déclaré par défaut. L'adresse (`url`) ne sort jamais de ce module vers un client : `publique()`
ne rend que ce qu'on montre à l'écran."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.harnais.contrat import IDENT_ASSISTANT, FicheSource

logger = logging.getLogger(__name__)

TYPES_CONNECTEUR = ("eligibilite",)


class Declaration(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(pattern=IDENT_ASSISTANT)
    type: str
    url: str = Field(min_length=1)
    titre: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    tables: list[str] = Field(min_length=1, max_length=20)
    exemples: list[str] = Field(default_factory=list, max_length=10)

    def fiche(self) -> FicheSource:
        return FicheSource(id=self.id, type="connecteur", titre=self.titre, description=self.description, exemples=self.exemples, relais=["reference"])


def declarations() -> dict[str, Declaration]:
    """Les connecteurs déclarés, par identifiant. Relue à chaque appel : la configuration peut changer en test."""
    brut = (settings.connecteurs or "").strip()
    if not brut:
        return {}
    try:
        liste = json.loads(brut)
    except ValueError:
        logger.warning("MYCOLLECTIONS_CONNECTEURS : JSON illisible, ignoré")
        return {}
    if not isinstance(liste, list):
        logger.warning("MYCOLLECTIONS_CONNECTEURS : un tableau est attendu, ignoré")
        return {}
    rendu: dict[str, Declaration] = {}
    for i, entree in enumerate(liste):
        try:
            d = Declaration.model_validate(entree)
        except ValidationError:
            logger.warning("MYCOLLECTIONS_CONNECTEURS : l'entrée %d est invalide, ignorée", i)
            continue
        if d.type not in TYPES_CONNECTEUR:
            logger.warning("MYCOLLECTIONS_CONNECTEURS : type « %s » inconnu (entrée %d), ignoré", d.type, i)
            continue
        if d.id in rendu:
            logger.warning("MYCOLLECTIONS_CONNECTEURS : l'identifiant « %s » est déclaré deux fois, la première entrée l'emporte", d.id)
            continue
        rendu[d.id] = d
    return rendu


def publique(d: Declaration) -> dict:
    """Ce que la liste des connecteurs montre : jamais l'adresse du service ni ses tables."""
    return {"id": d.id, "type": "connecteur", "titre": d.titre, "description": d.description, "exemples": d.exemples}
