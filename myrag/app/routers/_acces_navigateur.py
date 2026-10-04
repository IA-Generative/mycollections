"""Gardes des routes qu'un navigateur ouvre sans jeton : sources, graphe, articles.

Trois façons d'entrer, dans l'ordre :
1. la collection est publiée À TOUS dans l'assistant : tout compte de l'assistant la lit déjà,
   et l'outil « graphe » de l'assistant appelle ces routes de serveur à serveur ;
2. le lien porte une signature valide (`app.services.liens`), remise par le serveur à quelqu'un
   qui avait le droit de lire ;
3. l'appel porte un jeton valide, et son titulaire peut lire la collection.
Sinon : 401 sans jeton (avec un message qui dit quoi faire), 404 si le titulaire ne lit pas.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import CurrentUser, _bearer_scheme, current_user, verify_jwt
from app.config import settings
from app.services import access, liens

MESSAGE_401 = ("Ce lien n'est plus valable, ou n'a pas été remis par Mes collections : "
               "ouvrez la source depuis la collection.")


async def publiee_a_tous(collection: str) -> bool:
    """Publiée dans l'assistant pour tout compte connecté, et non archivée."""
    from app.database import async_session
    from app.models.db import Collection, Publication

    if not collection:
        return False
    async with async_session() as session:
        col = await session.get(Collection, collection)
        pub = await session.get(Publication, collection)
    return bool(col and pub and not col.archived_at and pub.state == "published"
                and pub.alias_enabled and pub.visibility == "all")


async def utilisateur_facultatif(credentials: HTTPAuthorizationCredentials | None) -> CurrentUser | None:
    """L'appelant s'il présente un jeton (un jeton invalide reste refusé), sinon None."""
    if credentials is None or not credentials.credentials:
        return None
    claims = verify_jwt(credentials)
    return await current_user(claims, credentials)


def peut_lire(fiche: dict | None, collection: str, user: CurrentUser) -> bool:
    if fiche is None:
        return access.can_write(name=collection, created_by=None, user_groups=user.groups, user_sub=user.sub)
    return access.can_read(name=collection, scope=fiche.get("scope"), scope_groups=fiche.get("scope_groups"),
                           created_by=fiche.get("created_by"), user_groups=user.groups, user_sub=user.sub)


async def exiger_lecture(collection: str, request: Request,
                         credentials: HTTPAuthorizationCredentials | None) -> None:
    if not settings.auth_enabled:
        return
    if await publiee_a_tous(collection):
        return
    q = request.query_params
    if liens.valide(liens.portee_graphe(collection), q.get("exp"), q.get("sig")):
        return
    user = await utilisateur_facultatif(credentials)
    if user is None:
        raise HTTPException(status_code=401, detail=MESSAGE_401)
    from app.services.collection_store import get_collection
    if not peut_lire(await get_collection(collection), collection, user):
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")


async def lecture_de_la_collection(collection: str, request: Request,
                                   credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> None:
    """Dépendance pour les routes dont la collection est dans le chemin."""
    await exiger_lecture(collection, request, credentials)


async def lecture_du_corpus(request: Request, corpus_id: str = "",
                            credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> None:
    """Dépendance pour les routes dont la collection est le paramètre `corpus_id`."""
    if corpus_id:
        await exiger_lecture(corpus_id, request, credentials)


async def acces_extrait(ident: str, request: Request,
                        credentials: HTTPAuthorizationCredentials | None) -> CurrentUser | None:
    """Un extrait ou un document d'OpenRAG : lien signé, ou jeton. Rend l'appelant (None si
    l'entrée s'est faite par signature ou sans authentification) : la route vérifie ensuite
    qu'il lit la collection de l'extrait."""
    if not settings.auth_enabled:
        return None
    q = request.query_params
    if liens.valide(liens.portee_extrait(ident), q.get("exp"), q.get("sig")):
        return None
    user = await utilisateur_facultatif(credentials)
    if user is None:
        raise HTTPException(status_code=401, detail=MESSAGE_401)
    return user
