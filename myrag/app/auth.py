"""Validation des jetons OIDC Keycloak (garde d'authentification du backend).

Vérifie la signature RS256 via le JWKS du realm, l'émetteur (iss) et
l'expiration. L'audience n'est PAS vérifiée : les access tokens Keycloak
portent souvent ``aud=account`` et le client effectif peut varier (front
public vs service account), ce qui rendrait une vérification stricte cassante.

Pilotage par ``AUTH_ENABLED`` (settings.auth_enabled) :
- ``false`` (défaut) → no-op (dev local, tests) ;
- ``true``  → jeton requis et validé sur les routes protégées.

C'est aussi le coupe-circuit : passer ``AUTH_ENABLED=false`` dans la configmap
puis redémarrer désactive la garde sans rebuild ni rollback.
"""

import logging

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger("myrag.auth")

# auto_error=False : on gère nous-mêmes le 401 (et le no-op quand auth désactivée).
_bearer_scheme = HTTPBearer(auto_error=False)

_jwks_client: "jwt.PyJWKClient | None" = None


def _issuer() -> str:
    return f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"


def _jwks_uri() -> str:
    return f"{_issuer()}/protocol/openid-connect/certs"


def _get_jwks_client() -> "jwt.PyJWKClient":
    global _jwks_client
    if _jwks_client is None:
        # PyJWKClient met les clés en cache : pas de fetch réseau à chaque requête.
        _jwks_client = jwt.PyJWKClient(_jwks_uri(), cache_keys=True)
    return _jwks_client


def verify_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Dépendance FastAPI : exige et valide un access token Keycloak.

    Dépendance *synchrone* → FastAPI l'exécute dans un threadpool, le fetch
    JWKS bloquant (mis en cache) n'impacte donc pas la boucle asyncio.
    """
    if not settings.auth_enabled:
        return {}

    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authentification requise")

    token = credentials.credentials
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=_issuer(),
            options={"verify_aud": False, "require": ["exp", "iat"]},
        )
        return claims
    except jwt.PyJWTError:
        # Pas de détail au client (évite de divulguer la raison exacte).
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré")
    except Exception:
        # JWKS injoignable, etc. : on échoue fermé (sécurité), 503 pour
        # distinguer d'un jeton invalide côté exploitation.
        logger.exception("Échec de validation JWT (JWKS injoignable ?)")
        raise HTTPException(status_code=503, detail="Service d'authentification indisponible")


# Liste de dépendances à passer aux routers protégés.
AUTH_REQUIRED = [Depends(verify_jwt)]


class CurrentUser:
    """Identité de l'appelant dérivée de l'access token (sub, username, groupes)."""

    __slots__ = ("sub", "username", "groups")

    def __init__(self, sub: str, username: str, groups: list[str]):
        self.sub = sub
        self.username = username
        self.groups = groups


def current_user(claims: dict = Depends(verify_jwt)) -> CurrentUser:
    """Dépendance FastAPI : identité + groupes Keycloak de l'appelant.

    Réutilise ``verify_jwt`` (mis en cache par FastAPI dans la requête, donc le
    JWT n'est validé qu'une fois même si la garde de routeur l'a déjà appelé).

    Quand l'auth est désactivée (dev/tests), renvoie un superadmin synthétique
    afin de préserver le comportement « tout visible » sans token.
    """
    if not settings.auth_enabled:
        root = settings.myrag_group_root.rstrip("/")
        return CurrentUser(sub="dev", username="dev", groups=[f"{root}/superadmin"])

    groups = claims.get("groups") or []
    if not isinstance(groups, list):
        groups = []
    return CurrentUser(
        sub=claims.get("sub", ""),
        username=claims.get("preferred_username", "") or claims.get("email", ""),
        groups=[g for g in groups if isinstance(g, str)],
    )
