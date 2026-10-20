"""Un débit par personne et par minute, en mémoire du processus (une limite par pod).

Même mécanique que la recherche v1 (`routers/recherche.py`), réutilisable par d'autres routes :
`compter(cle)` rend `None` tant que le plafond tient, sinon le nombre de secondes à attendre,
à porter dans `Retry-After`. Un plafond nul ou négatif : pas de limite."""

from __future__ import annotations

import time
from collections.abc import Callable


class Fenetre:
    def __init__(self, plafond: Callable[[], int], *, taille_max: int = 10000):
        self._plafond = plafond
        self._taille_max = taille_max
        self._comptes: dict[str, tuple[int, int]] = {}

    def compter(self, cle: str, *, maintenant: float | None = None) -> int | None:
        plafond = self._plafond()
        if plafond <= 0:
            return None
        t = time.time() if maintenant is None else maintenant
        minute = int(t // 60)
        vue, compte = self._comptes.get(cle, (minute, 0))
        compte = compte + 1 if vue == minute else 1
        if len(self._comptes) > self._taille_max:
            for k in [k for k, (m, _) in self._comptes.items() if m != minute]:
                del self._comptes[k]
        self._comptes[cle] = (minute, compte)
        return 60 - int(t) % 60 if compte > plafond else None
