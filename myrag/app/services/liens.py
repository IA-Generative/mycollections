"""Liens signés : ce qu'un navigateur ouvre sans pouvoir porter de jeton.

Une source citée dans une réponse s'ouvre dans un onglet neuf, le graphe vit dans une iframe,
un article se lit par un lien : aucun ne porte d'en-tête `Authorization`. Avant le diagnostic
d'octobre 2026, ces routes étaient donc ouvertes à tous, jeton admin d'OpenRAG compris.

Désormais le serveur, qui sait que l'appelant a le droit de lire, signe le lien qu'il lui
remet : `?exp=<epoch>&sig=<hmac>`. La signature porte sur une PORTÉE (`extrait:<id>`,
`graphe:<collection>`…), pas sur l'adresse entière : les paramètres d'affichage peuvent
changer, la portée non. Elle expire (12 h par défaut) ; passé ce délai, l'application relit la
source avec le jeton de la session.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from app.config import settings

DUREE_S = 12 * 3600


def _cle() -> bytes | None:
    if settings.myrag_liens_sel:
        return settings.myrag_liens_sel.encode()
    if settings.myrag_pseudo_sel:
        return hmac.new(settings.myrag_pseudo_sel.encode(), b"myrag-liens", hashlib.sha256).digest()
    return None


def _sig(cle: bytes, portee: str, exp: int) -> str:
    return hmac.new(cle, f"{portee}|{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def parametres(portee: str, duree_s: int = DUREE_S) -> dict[str, str]:
    """Les paramètres à ajouter au lien ; vide si aucune clé n'est configurée."""
    cle = _cle()
    if cle is None:
        return {}
    exp = int(time.time()) + duree_s
    return {"exp": str(exp), "sig": _sig(cle, portee, exp)}


def signer(url: str, portee: str, duree_s: int = DUREE_S) -> str:
    """`url` avec ses paramètres de signature (après ceux qu'elle porte déjà)."""
    p = parametres(portee, duree_s)
    if not p:
        return url
    return url + ("&" if "?" in url else "?") + urlencode(p)


def valide(portee: str, exp: str | None, sig: str | None) -> bool:
    cle = _cle()
    if cle is None or not exp or not sig:
        return False
    try:
        echeance = int(exp)
    except ValueError:
        return False
    if echeance < time.time():
        return False
    return hmac.compare_digest(_sig(cle, portee, echeance), sig)


def portee_extrait(ident: str) -> str:
    return f"extrait:{ident}"


def portee_graphe(collection: str) -> str:
    """Une portée pour toute la vue d'une collection : visualiseur, données, articles."""
    return f"graphe:{collection}"
