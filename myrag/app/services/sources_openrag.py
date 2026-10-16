"""Les sources d'une réponse d'OpenRAG, dans ses deux formes (2.2.1 et 2.3.1).

- `extra` : une chaîne JSON en 2.2.1, un objet en 2.3.1 (mêmes clés).
- Une source documentaire : métadonnées au premier niveau en 2.2.1 ; sous `chunk` en 2.3.1
  (`_id` compris), seuls `source_type`, `chunk_url`, `file_url` et les scores restant au premier
  niveau. Les sources web ne changent pas.

On ramène tout à la forme à plat de 2.2.1, une fois, juste après la lecture d'`extra` : le reste
de l'application (noms, libellés, liens signés, puces du front) ne voit qu'une forme.
"""

from __future__ import annotations

import json


def aplatir_source(s):
    """Source OpenRAG 2.3 (métadonnées sous `chunk`) → forme à plat de 2.2.1 ; inchangée sinon.
    Les clés du premier niveau l'emportent."""
    c = s.get("chunk") if isinstance(s, dict) else None
    if not isinstance(c, dict):
        return s
    return {**c, **{k: v for k, v in s.items() if k != "chunk"}}


def lire_extra(extra) -> dict:
    """`extra` décodé : chaîne JSON ou objet ; `{}` s'il est absent, vide ou illisible."""
    if isinstance(extra, str):
        try:
            extra = json.loads(extra) if extra else {}
        except ValueError:
            return {}
    return extra if isinstance(extra, dict) else {}


def sources_de(extra, cle: str = "sources") -> list:
    """La liste `cle` d'`extra` (chaîne ou objet), chaque source aplatie ; `[]` si illisible."""
    sources = lire_extra(extra).get(cle)
    if not isinstance(sources, list):
        return []
    return [aplatir_source(s) for s in sources]
