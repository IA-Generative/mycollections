"""Garde-fous d'entrée partagés — anti path traversal & anti SSRF.

Centralisé pour que tous les points d'entrée appliquent la même validation.
Aucune dépendance externe.
"""

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException


def safe_filename(filename: str) -> str:
    """Réduit un nom de fichier (potentiellement contrôlé par l'attaquant) à un
    basename sûr. Supprime toute composante de répertoire et rejette les
    séquences de traversée. HTTP 400 si rien d'exploitable ne subsiste.
    """
    base = Path(str(filename)).name.strip()
    if not base or base in (".", "..") or "/" in base or "\\" in base:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    return base


def ensure_within(base_dir: Path, candidate: Path) -> Path:
    """Confirme que `candidate` se résout à l'intérieur de `base_dir`.

    Rejette toute valeur (segment de collection, etc.) qui ferait sortir du
    répertoire autorisé via `..` ou un chemin absolu. HTTP 400 sinon.
    """
    base = base_dir.resolve()
    target = candidate.resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail="Chemin hors du répertoire autorisé")
    return target


def reject_path_traversal(value: str, *, field: str = "identifiant") -> str:
    """Rejette les séquences de traversée dans un segment destiné à une URL
    upstream (chunk_id, file_id, filepath…). Autorise les `/` internes mais
    interdit tout composant `..` ou un chemin absolu. HTTP 400 sinon.
    """
    if not value or value.startswith("/") or "\\" in value:
        raise HTTPException(status_code=400, detail=f"{field} invalide")
    if ".." in value.split("/"):
        raise HTTPException(status_code=400, detail=f"{field} invalide")
    return value


# --- Anti-SSRF -------------------------------------------------------------

def assert_public_http_url(url: str) -> str:
    """Valide une URL fournie par l'utilisateur avant un fetch côté serveur.

    - schéma http/https uniquement (bloque file://, gopher://, etc.) ;
    - résout le DNS et rejette toute IP loopback / privée / link-local /
      réservée (bloque 127.0.0.1, 169.254.169.254, 10/8, 192.168/16, services
      internes du cluster…).

    Retourne l'URL inchangée si elle est sûre, sinon HTTP 400.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Schéma d'URL non autorisé (http/https uniquement)")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="URL invalide")

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Hôte introuvable")

    for family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="Cible d'URL non autorisée (adresse interne)")
    return url
