"""Le serveur MCP des assistants de recherche, en transport Streamable HTTP, monté sur `/mcp`.

La porte est celle de la recherche v1 : jeton Bearer de la personne (signature, émetteur,
**audience** — `audience_acceptee` —, groupe exigé), puis l'identité est relayée aux outils ; sans
jeton, refus. Le drapeau `assistants` de capacites.json à faux ⇒ 404, comme les routes des
assistants. Sans le paquet `mcp` (extra `mcp`), rien n'est monté. Mode sans état : une requête, une
session, aucun état partagé entre pods.

Tourne comme une application ASGI à part entière (et non comme une route FastAPI) : le transport
écrit lui-même sa réponse, et un client MCP attend l'adresse exacte `/mcp`."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.types import Receive, Scope, Send

from app.auth import CurrentUser, _exiger_le_groupe, audience_acceptee, current_user, decoder_le_jeton
from app.config import settings
from app.services import capacites
from app.services.pseudo import SelAbsent, condenser

logger = logging.getLogger("myrag.mcp")

CHEMIN = "/mcp"
_utilisateur: contextvars.ContextVar[CurrentUser] = contextvars.ContextVar("mcp_utilisateur")


async def _repondre(send: Send, statut: int, code: str, message: str, entetes: dict[str, str] | None = None) -> None:
    corps = json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False).encode()
    tete = [(b"content-type", b"application/json"), (b"cache-control", b"no-store"), *[(k.lower().encode(), v.encode()) for k, v in (entetes or {}).items()]]
    await send({"type": "http.response.start", "status": statut, "headers": tete})
    await send({"type": "http.response.body", "body": corps})


async def _identifier(scope: Scope) -> CurrentUser:
    """La personne du jeton, ou une `HTTPException`. Sans authentification (développement), la personne de développement."""
    if not settings.auth_enabled:
        return await current_user({}, None)
    brut = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
    schema, _, jeton = brut.partition(" ")
    if schema.lower() != "bearer" or not jeton.strip():
        raise HTTPException(401, "Jeton absent", headers={"WWW-Authenticate": "Bearer"})
    jeton = jeton.strip()
    claims = await asyncio.to_thread(decoder_le_jeton, jeton)  # le JWKS se lit en bloquant (en cache)
    if not audience_acceptee(claims):
        logger.warning("MCP refusé : audience non acceptée (azp=%s)", str(claims.get("azp", ""))[:64])
        raise HTTPException(403, "Ce jeton n'est pas destiné à Mes collections")
    _exiger_le_groupe(claims)
    user = await current_user(claims, HTTPAuthorizationCredentials(scheme="Bearer", credentials=jeton))
    if not user.sub:
        raise HTTPException(401, "Jeton sans identité (sub)")
    return user


class ApplicationMCP:
    """L'application ASGI de `/mcp`."""

    def __init__(self):
        from app.mcp.serveur import serveur

        self._serveur = serveur(_utilisateur.get)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        if scope["type"] != "http":
            return
        if (await capacites.lire_async()).get("assistants") is not True:
            return await _repondre(send, 404, "not_found", "Fonction désactivée : « assistants » n'est pas déclarée dans capacites.json")
        try:
            user = await _identifier(scope)
            condenser(user.sub)  # le sel des identités : sans lui, ni recherche ni journal
        except HTTPException as e:
            return await _repondre(
                send, e.status_code, "invalid_token" if e.status_code == 401 else "forbidden" if e.status_code == 403 else "unavailable", str(e.detail), dict(e.headers or {})
            )
        except SelAbsent:
            return await _repondre(send, 503, "unavailable", "Le service n'est pas configuré (sel des identités absent)")
        _utilisateur.set(user)
        # Sans état : un gestionnaire par requête (sa boucle de tâches ne sert qu'une fois), le serveur est partagé.
        gestionnaire = StreamableHTTPSessionManager(app=self._serveur, json_response=True, stateless=True)
        async with gestionnaire.run():
            await gestionnaire.handle_request(scope, receive, send)


def monter(application) -> bool:
    """Monte `/mcp` sur l'application FastAPI. Faux (et rien de monté) si le paquet `mcp` manque."""
    try:
        from starlette.routing import Route

        mcp_app = ApplicationMCP()
    except ImportError:
        logger.warning("Paquet « mcp » absent : le serveur MCP des assistants n'est pas monté (extra `mcp`)")
        return False
    application.router.routes.append(Route(CHEMIN, endpoint=mcp_app))
    return True
