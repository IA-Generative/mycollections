"""Le seul point de sortie réseau des connecteurs d'amorces — un point que les tests
remplacent, et que la politique de sortie du cluster nomme hôte par hôte."""

from __future__ import annotations

import httpx

DELAI_S = 180.0
TAILLE_MAX = 400 * 1024 * 1024  # 400 Mio : un ZIP mensuel des TA fait ~60 Mio


async def telecharger(url: str, *, entetes: dict | None = None) -> bytes:
    """Télécharge une ressource entière. Lève httpx.HTTPError en cas d'échec."""
    async with httpx.AsyncClient(timeout=DELAI_S, follow_redirects=True) as client:
        reponse = await client.get(url, headers=entetes or {})
        reponse.raise_for_status()
        if len(reponse.content) > TAILLE_MAX:
            raise ValueError(f"ressource trop volumineuse : {len(reponse.content)} octets")
        return reponse.content


async def lire_json(url: str, *, entetes: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        reponse = await client.get(url, headers=entetes or {})
        reponse.raise_for_status()
        return reponse.json()
