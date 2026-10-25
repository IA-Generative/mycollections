"""Ce qui distingue une source dans le moteur d'import et de synchronisation partagé.

Le moteur (fiche par document, tri nouveau/changé/inchangé/disparu, dossier d'attente, envois
parallèles, doublons, conversion, qualité, relais du jeton) est né pour Résana
(`routers/sources_resana.py`). Fichiers le réutilise tel quel : son client parle comme celui du
service d'export Résana. Ce qui change d'une source à l'autre tient dans un `Profil`, posé pour la
durée d'une passe (`sous`), et lu par le moteur aux quelques endroits où la source se voit : le
préfixe des identifiants dans l'index, le dossier d'attente, la source écrite dans les métadonnées
et le journal, le message d'une source saturée.

Le profil par défaut est celui de Résana : rien ne change pour lui. Voir docs/fichiers.md.
"""

from __future__ import annotations

from collections.abc import Awaitable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Profil:
    #: `source_type` des collections, `source` des métadonnées et du journal.
    source: str
    #: Le nom de la source dans les phrases (« Résana renvoie des fichiers vides… »).
    nom: str
    #: Le début de l'identifiant d'un document chez l'indexeur. Celui de Résana ne change JAMAIS :
    #: un autre préfixe renverrait tous les documents déjà indexés.
    prefixe_index: str
    #: Le dossier (sous DATA_DIR) où attendent les fichiers d'une passe.
    dossier_attente: str


RESANA = Profil(source="resana", nom="Résana", prefixe_index="resana-", dossier_attente="_resana_attente")

_PROFIL: ContextVar[Profil] = ContextVar("profil_de_synchro", default=RESANA)


def profil() -> Profil:
    """Le profil de la passe en cours (Résana hors d'une passe d'une autre source)."""
    return _PROFIL.get()


async def sous(p: Profil, travail: Awaitable[T]) -> T:
    """Joue `travail` (une coroutine du moteur) sous le profil `p` : la tâche de fond qui l'exécute
    voit ce profil, et lui seul (le contexte d'une tâche est le sien)."""
    jeton = _PROFIL.set(p)
    try:
        return await travail
    finally:
        _PROFIL.reset(jeton)
