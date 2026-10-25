"""Les collections importées d'une source avec les droits de la personne qui importe.

Résana et Fichiers suivent les mêmes règles (docs/resana.md, docs/fichiers.md) : la collection naît
privée à l'importeur, sa portée et sa source ne changent pas par la fiche, elle se réindexe en
relisant la source (pas de copie gardée), et elle ne s'ouvre qu'à un groupe choisi, avec la
confirmation que ses membres ont les droits dans la source.
"""

from __future__ import annotations

SOURCES_IMPORTEES = ("resana", "fichiers")
NOMS = {"resana": "Résana", "fichiers": "Fichiers"}


def source_importee(col: dict | None) -> str | None:
    """`resana` ou `fichiers` pour une collection importée, sinon None."""
    source = (col or {}).get("source_type")
    return source if source in SOURCES_IMPORTEES else None


def nom(source: str | None) -> str:
    return NOMS.get(source or "", source or "")
