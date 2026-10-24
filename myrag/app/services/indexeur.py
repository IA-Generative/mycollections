"""L'indexeur : le moteur qui reçoit les documents entiers, les lit, les découpe et les rend
cherchables. Aujourd'hui OpenRAG ; demain un autre, sans toucher aux sources (Résana, dépôt d'un
fichier) qui ne parlent qu'à cette interface.

Ce que Mes collections attend d'un indexeur, et rien de plus :

- `preparer(collection)` : l'espace qui accueille les documents d'une collection existe ;
- `envoyer(...)` : confier un document entier, sous un identifiant choisi par Mes collections
  (stable : un renvoi après coupure retombe sur le même document ; `DejaPresent` le signale) ;
- `suivre(tache)` : où en est la lecture (`en_cours`, `lu`, `echec` avec sa raison) ;
- `retirer(collection, identifiant)` : un document sort de l'index (absent : pas une erreur) ;
- `vider(collection)` : toute la collection sort de l'index.

La recherche et la réponse (côté assistants) ont leur propre abstraction : les connecteurs du
harnais (ADR-0003). Le découpage par Mes collections des fichiers texte (`_upload_chunks_background`)
reste propre à OpenRAG pour l'instant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.services.openrag_client import OpenRAGClient

Lecture = Literal["en_cours", "lu", "echec"]

_ETATS_LUS = ("COMPLETED", "SUCCESS")
_ETATS_ECHOUES = ("FAILED", "CANCELLED")


class DejaPresent(Exception):
    """L'indexeur a déjà un document sous cet identifiant (renvoi après une coupure)."""


class Refuse(Exception):
    """L'indexeur refuse le document ; `statut` à la manière HTTP (413, 415, 422…)."""

    def __init__(self, statut: int | None):
        self.statut = statut
        super().__init__(f"refusé ({statut})")


@dataclass(frozen=True)
class Envoi:
    identifiant: str
    #: La tâche de lecture à suivre ; vide si le document est lu sur-le-champ.
    tache: str


@dataclass(frozen=True)
class Suivi:
    lecture: Lecture
    raison: str = ""


class Indexeur(Protocol):
    nom: str

    async def preparer(self, collection: str) -> None: ...

    async def envoyer(self, collection: str, nom: str, contenu: bytes, *, mime: str, metadata: dict, identifiant: str | None = None) -> Envoi: ...

    async def suivre(self, tache: str) -> Suivi: ...

    async def retirer(self, collection: str, identifiant: str) -> None: ...

    async def vider(self, collection: str) -> None: ...


class IndexeurOpenRAG:
    """L'indexeur OpenRAG : une partition par collection, un fichier par document."""

    nom = "openrag"

    def __init__(self, client: OpenRAGClient):
        self.client = client

    async def preparer(self, collection: str) -> None:
        await self.client.create_partition(collection)

    async def envoyer(self, collection: str, nom: str, contenu: bytes, *, mime: str, metadata: dict, identifiant: str | None = None) -> Envoi:
        try:
            envoi = await self.client.upload_document(collection, nom, contenu, mime, metadata=metadata, file_id=identifiant)
        except httpx.HTTPStatusError as e:
            statut = e.response.status_code if e.response is not None else None
            if statut == 409:
                raise DejaPresent(identifiant or "") from None
            raise Refuse(statut) from None
        return Envoi(identifiant=envoi.file_id, tache=envoi.task_id)

    async def suivre(self, tache: str) -> Suivi:
        etat = str((await self.client.task_state(tache)).task_state or "").upper()
        if etat in _ETATS_LUS:
            return Suivi("lu")
        if etat in _ETATS_ECHOUES:
            return Suivi("echec", await self.client.task_error(tache) or etat)
        return Suivi("en_cours")

    async def retirer(self, collection: str, identifiant: str) -> None:
        await self.client.delete_file(collection, identifiant)

    async def vider(self, collection: str) -> None:
        await self.client.delete_partition(collection)
