"""L'indexeur : le moteur qui reçoit les documents entiers, les lit, les découpe et les rend
cherchables. Aujourd'hui OpenRAG ; demain un autre, sans toucher aux sources (Résana, dépôt d'un
fichier) qui ne parlent qu'à cette interface.

Ce que Mes collections attend d'un indexeur, et rien de plus :

- `preparer(collection)` : l'espace qui accueille les documents d'une collection existe ;
- `envoyer(...)` : confier un document entier, sous un identifiant choisi par Mes collections
  (stable : un renvoi après coupure retombe sur le même document ; `DejaPresent` le signale) ;
- `suivre(tache)` : où en est la lecture (`en_cours`, `lu`, `echec` avec sa raison), et, une fois
  lu, ce que vaut l'indexation (`qualite` : complète, sans contexte pour une part des passages…) ;
- `retirer(collection, identifiant)` : un document sort de l'index (absent : pas une erreur) ;
- `vider(collection)` : toute la collection sort de l'index.

La recherche et la réponse (côté assistants) ont leur propre abstraction : les connecteurs du
harnais (ADR-0003). Le découpage par Mes collections des fichiers texte (`_upload_chunks_background`)
reste propre à OpenRAG pour l'instant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

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


#: Ce que vaut l'indexation d'un document, du meilleur au pire :
#: - `complet` : lu, chaque passage a son contexte ;
#: - `degrade` : lu, mais une étape d'enrichissement a échoué (description d'images…) ;
#: - `sans_contexte` : lu, mais une part des passages n'a pas le contexte que le modèle devait
#:   leur ajouter (quota dépassé…) : ils se retrouvent moins bien ;
#: - `sans_texte` : rien à indexer, le plus souvent un scan sans OCR ;
#: - `echec` : non lu, pour une autre raison.
ETATS_QUALITE = ("complet", "degrade", "sans_contexte", "sans_texte", "echec")
#: Ce que l'indexeur dit d'un document sans texte exploitable (OpenRAG : `NoIndexableContentError`).
_SANS_TEXTE = ("NO_INDEXABLE_CONTENT", "NoIndexableContent")


def qualite_lecture(details: dict[str, Any] | None) -> dict | None:
    """La qualité d'un document lu, d'après le détail de sa tâche. OpenRAG 2.3 marque les étapes en
    échec (`degraded_stages`, liste ou dictionnaire) et compte les passages sans contexte
    (`contextualization` : `total`, `failed`). Rien de tout cela : `None` (on ne sait pas dire)."""
    if not isinstance(details, dict):
        return None
    ctx = details.get("contextualization") if isinstance(details.get("contextualization"), dict) else {}
    etapes = details.get("degraded_stages") or []
    etapes = sorted(etapes) if isinstance(etapes, (list, dict)) else []
    passages, sans_contexte = ctx.get("total"), ctx.get("failed")
    if isinstance(sans_contexte, int) and sans_contexte > 0:
        etat = "sans_contexte"
    elif "contextualize" in etapes:
        etat = "sans_contexte"
    elif etapes:
        etat = "degrade"
    elif "degraded_stages" in details or ctx or "parse_backend" in details:
        etat = "complet"
    else:
        return None
    q: dict = {"etat": etat}
    if isinstance(passages, int):
        q["passages"] = passages
    if isinstance(sans_contexte, int):
        q["sans_contexte"] = sans_contexte
    if etapes:
        q["etapes"] = etapes
    # Le parseur le dit depuis le repli OCR d'OpenRAG (#152) : lu par OCR, et pages perdues.
    if details.get("ocr") is True:
        q["ocr"] = True
    if isinstance(details.get("ocr_failed_pages"), int) and details["ocr_failed_pages"] > 0:
        q["pages_perdues"] = details["ocr_failed_pages"]
    return q


def qualite_echec(raison: str) -> dict:
    """La qualité d'un document que l'indexeur n'a pas lu : sans texte (un scan, le plus souvent) ou
    en échec."""
    return {"etat": "sans_texte" if any(m in (raison or "") for m in _SANS_TEXTE) else "echec"}


@dataclass(frozen=True)
class Suivi:
    lecture: Lecture
    raison: str = ""
    #: Une fois lu : ce que vaut l'indexation (`qualite_lecture`) ; `None` si l'indexeur ne le dit pas.
    qualite: dict | None = None


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
        tache_ = await self.client.task_state(tache)
        etat = str(tache_.task_state or "").upper()
        if etat in _ETATS_LUS or etat == "COMPLETED_DEGRADED":
            return Suivi("lu", qualite=qualite_lecture(tache_.details))
        if etat in _ETATS_ECHOUES:
            return Suivi("echec", await self.client.task_error(tache) or etat)
        return Suivi("en_cours")

    async def retirer(self, collection: str, identifiant: str) -> None:
        await self.client.delete_file(collection, identifiant)

    async def vider(self, collection: str) -> None:
        await self.client.delete_partition(collection)
