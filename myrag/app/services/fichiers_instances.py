"""Les instances de Fichiers (Drive de La Suite numérique) déclarées par configuration.

`MYCOLLECTIONS_FICHIERS_INSTANCES` est un tableau JSON ; chaque instance dit où la joindre, comment
lire ses fichiers, et le niveau de sensibilité le plus haut qu'elle est censée contenir
(`sensibilite_max`) : les documents qu'on en importe sont réputés à ce niveau (docs/fichiers.md).

Une déclaration illisible ou en double est ignorée, journalisée sans son contenu : une faute de
frappe n'éteint pas l'application. Sans déclaration, `DRIVE_URL` (réglage d'avant) donne une
instance implicite `drive`. Les adresses ne sortent jamais vers un client : `publique()` ne rend que
ce que l'écran montre.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.config import settings
from app.services import access
from app.services.chunker import Sensitivity

logger = logging.getLogger(__name__)

IDENT = r"^[a-z][a-z0-9]{1,19}$"


class Instance(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    #: Court et stable : il entre dans l'identifiant des collections (`fichiers-<id>-…`).
    id: str = Field(pattern=IDENT)
    titre: str = Field(min_length=1, max_length=120)
    #: Où Mes collections joint l'API (service interne dans un cluster, sinon l'adresse publique).
    url: str = Field(min_length=1)
    #: Le nom public de l'instance : en-tête `Host` quand `url` est un service interne, et
    #: adresse des liens de consultation (`https://<hote_public>/explorer/items/files/<id>`).
    hote_public: str = Field(default="", max_length=255)
    #: Le stockage objet derrière `/media/` (`https://<point S3>/<seau>`) : Mes collections y lit les
    #: octets avec la signature que rend Drive (`media-auth`), comme le fait l'ingress. Vide ⇒ on
    #: suit l'adresse publique du fichier (`/media/…`), avec le jeton de la personne.
    stockage_url: str = Field(default="", max_length=500)
    #: Le niveau le plus haut que l'instance est censée contenir : le plancher de ses collections.
    sensibilite_max: Sensitivity = Sensitivity.INTERNAL
    #: Ce qu'on dit de l'instance à l'écran (« internet, bêta », « RIE, on premise »).
    zone: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)
    #: Réservée à ces groupes (chemins complets) ; vide : à toute personne connectée.
    groupes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("url", "stockage_url")
    @classmethod
    def _adresse(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("adresse http(s) attendue")
        return v.rstrip("/")

    @field_validator("groupes")
    @classmethod
    def _chemins_complets(cls, valeurs: list[str]) -> list[str]:
        if any(not g.startswith("/") for g in valeurs):
            raise ValueError("un groupe se donne en chemin complet (« /g/… »)")
        return valeurs

    def ouverte_a(self, groupes: list[str] | None) -> bool:
        if not self.groupes or access.is_superadmin(groupes):
            return True
        return bool(set(access.chemins(groupes)) & set(self.groupes))

    @property
    def origine_publique(self) -> str:
        """`https://<hote_public>`, ou l'adresse d'appel quand l'instance est jointe par son nom public."""
        return f"https://{self.hote_public}" if self.hote_public else self.url

    def url_consultation(self, item_id: str) -> str:
        """Le fichier ouvert dans Fichiers (la page d'aperçu de l'explorateur)."""
        return f"{self.origine_publique}/explorer/items/files/{item_id}"

    def url_dossier(self, item_id: str) -> str:
        return f"{self.origine_publique}/explorer/items/{item_id}"

    def publique(self) -> dict:
        return {
            "id": self.id,
            "titre": self.titre,
            "zone": self.zone,
            "description": self.description,
            "sensibilite_max": self.sensibilite_max.value,
            "hote": self.hote_public or self.url.split("://", 1)[-1],
        }


def _implicite() -> Instance | None:
    if not settings.drive_url:
        return None
    try:
        return Instance(id="drive", titre="Mes fichiers", url=settings.drive_url, hote_public=settings.drive_public_host or "", sensibilite_max=Sensitivity.INTERNAL)
    except ValidationError:
        logger.warning("DRIVE_URL illisible : pas d'instance de Fichiers implicite")
        return None


def instances() -> dict[str, Instance]:
    """Les instances déclarées, par identifiant (relues à chaque appel : la configuration peut
    changer en test)."""
    brut = (settings.fichiers_instances or "").strip()
    if not brut:
        i = _implicite()
        return {i.id: i} if i else {}
    try:
        donnees = json.loads(brut)
    except ValueError:
        logger.warning("MYCOLLECTIONS_FICHIERS_INSTANCES illisible : aucune instance")
        return {}
    if not isinstance(donnees, list):
        logger.warning("MYCOLLECTIONS_FICHIERS_INSTANCES n'est pas un tableau : aucune instance")
        return {}
    rendu: dict[str, Instance] = {}
    for rang, brute in enumerate(donnees):
        try:
            i = Instance.model_validate(brute)
        except ValidationError as e:
            logger.warning("instance de Fichiers n°%d ignorée : %s", rang, ", ".join(".".join(map(str, err["loc"])) for err in e.errors()))
            continue
        if i.id in rendu:
            logger.warning("instance de Fichiers en double ignorée : %s", i.id)
            continue
        rendu[i.id] = i
    return rendu


def instance(ident: str) -> Instance | None:
    return instances().get(ident)


def lisibles_par(groupes: list[str] | None) -> list[Instance]:
    return [i for i in instances().values() if i.ouverte_a(groupes)]
