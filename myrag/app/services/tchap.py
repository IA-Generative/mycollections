"""Le lien Tchap d'un appel : un salon pour échanger, jamais une adresse de messagerie.

Accepté : `https`, un hôte de la liste blanche (`entraide_tchap_hotes`, hôte exact), sans
identifiants ni port, sans chemin ni paramètres, et un fragment `#/room/<salon>:<serveur>` — la
forme des liens de salon de Tchap. Tout le reste est refusé avec un message qui dit quoi faire.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.config import settings

_SALON = re.compile(r"^/room/[!#][A-Za-z0-9._=+\-]{1,120}:[A-Za-z0-9.\-]{1,120}$")
_LONGUEUR_MAX = 300


def hotes_autorises() -> set[str]:
    return {h.strip().lower() for h in settings.entraide_tchap_hotes.split(",") if h.strip()}


def valider(lien: str | None) -> str | None:
    """Le lien nettoyé, ou None s'il est vide ; ValueError (message lisible) s'il n'est pas admis."""
    lien = (lien or "").strip()
    if not lien:
        return None
    if len(lien) > _LONGUEUR_MAX or re.search(r"\s", lien):
        raise ValueError("Le lien Tchap n'a pas la forme attendue")
    try:
        u = urlsplit(lien)
        port = u.port
    except ValueError:
        raise ValueError("Le lien Tchap n'a pas la forme attendue")
    hotes = hotes_autorises()
    if u.scheme != "https":
        raise ValueError("Le lien Tchap commence par https://")
    if u.username is not None or u.password is not None or port not in (None, 443):
        raise ValueError("Le lien Tchap ne contient ni identifiant ni port")
    if (u.hostname or "").lower() not in hotes:
        raise ValueError("Ce lien n'est pas un lien Tchap reconnu : collez le lien d'un salon Tchap")
    if u.path not in ("", "/") or u.query:
        raise ValueError("Le lien Tchap est celui d'un salon, sans paramètres")
    if not _SALON.match(u.fragment):
        raise ValueError("Collez le lien d'invitation d'un salon Tchap (jamais une adresse de messagerie)")
    return f"https://{u.hostname.lower()}/#{u.fragment}"
