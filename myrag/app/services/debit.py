"""Une seule limite de débit vers le modèle, pour tout le processus.

La passerelle compte son quota PAR JETON : la génération de questions et le juge de la mesure de
qualité partagent le même jeton, donc la même fenêtre. Chacun prend une place ici avant d'appeler.
`prendre()` bloque le fil appelant ; côté asyncio, l'appeler par `asyncio.to_thread`.
"""

from __future__ import annotations

import threading

from app.config import settings
from app.generation.resultats import Debit

_verrou = threading.Lock()
_partage: Debit | None = None


def partage() -> Debit:
    """Le débit du processus, recréé si le réglage a changé (tests, rechargement)."""
    global _partage
    with _verrou:
        voulu = max(0, int(settings.generation_appels_par_minute or 0))
        if _partage is None or _partage.par_minute != voulu:
            _partage = Debit(voulu)
        return _partage
