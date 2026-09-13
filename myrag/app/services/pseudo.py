"""Le condensé des identités : HMAC-SHA256(sel, sub), jamais le `sub` en clair.

Même sel que le bus de la bêta (Secret `obs-pseudo-salt`) : une même personne a le
même condensé dans `soutien`, `abonnement` et dans `message_testeur` de la cloche.
Sans sel, on refuse d'écrire — jamais d'identité en clair par défaut.
"""

from __future__ import annotations

import hashlib
import hmac

from app.config import settings


class SelAbsent(RuntimeError):
    """Le service n'est pas configuré pour condenser : les routes répondent 503."""


def condenser(sub: str, sel: str | None = None) -> str:
    sel = settings.myrag_pseudo_sel if sel is None else sel
    if not sel:
        raise SelAbsent("MYRAG_PSEUDO_SEL absent : le condensé des identités n'est pas configuré")
    if not sub:
        raise ValueError("identité vide")
    return hmac.new(sel.encode("utf-8"), sub.encode("utf-8"), hashlib.sha256).hexdigest()
