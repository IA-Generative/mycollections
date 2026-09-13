"""Chercher les demandes proches d'un titre — pour soutenir plutôt que doublonner.

Portable SQLite/PostgreSQL et suffisant pour le volume de la bêta : normalisation
(minuscules, sans accents, mots de trois lettres et plus), Jaccard sur les mots et
ratio de séquence, on garde le meilleur des deux.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

SEUIL_SIMILARITE = 0.45
_MOTS_VIDES = {"des", "les", "une", "pour", "sur", "dans", "par", "avec", "aux", "national", "nationale"}


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def mots(texte: str) -> set[str]:
    return {m for m in normaliser(texte).split() if len(m) >= 3 and m not in _MOTS_VIDES}


def similarite(a: str, b: str) -> float:
    ma, mb = mots(a), mots(b)
    jaccard = len(ma & mb) / len(ma | mb) if (ma or mb) else 0.0
    ratio = difflib.SequenceMatcher(None, normaliser(a), normaliser(b)).ratio()
    return round(max(jaccard, ratio), 3)


def candidats(titre: str, demandes: list[dict], seuil: float = SEUIL_SIMILARITE) -> list[dict]:
    """Les demandes proches, les plus proches d'abord, chacune avec sa `similarite`."""
    trouvees = []
    for d in demandes:
        s = similarite(titre, d.get("titre", ""))
        if s >= seuil:
            trouvees.append({**d, "similarite": s})
    trouvees.sort(key=lambda d: d["similarite"], reverse=True)
    return trouvees
