"""Le relais du fil d'avancement vers la cloche de la barre commune.

myrag ne connaît que des condensés ; le bus les accepte tels quels (même sel) sur
`POST /_beta/messages`, sous le secret partagé. Best-effort et hors transaction : un bus
muet ne reprend jamais un geste déjà écrit.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger("myrag.relais")
CORPS_MAX = 500
_taches: set[asyncio.Task] = set()


async def envoyer(destinataires: list[str], corps: str, app: str = "mescollections") -> bool:
    destinataires = [d for d in dict.fromkeys(destinataires) if d]
    if not (settings.bus_url and settings.bus_secret and destinataires and corps.strip()):
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{settings.bus_url.rstrip('/')}/_beta/messages",
                                  json={"destinataires": destinataires, "corps": corps.strip()[:CORPS_MAX], "app": app},
                                  headers={"X-Bus-Secret": settings.bus_secret})
        if r.status_code >= 300:
            logger.warning("relais vers la cloche refusé : %s %s", r.status_code, r.text[:160])
            return False
        return True
    except httpx.HTTPError as e:
        logger.warning("relais vers la cloche impossible : %s", e)
        return False


def planifier(destinataires: list[str], corps: str, app: str = "mescollections") -> None:
    """Depuis une route : on n'attend pas la cloche."""
    try:
        boucle = asyncio.get_running_loop()
    except RuntimeError:
        return
    t = boucle.create_task(envoyer(destinataires, corps, app))
    _taches.add(t)
    t.add_done_callback(_taches.discard)
