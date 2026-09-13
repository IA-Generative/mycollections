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

Deux dispositifs s'ajoutent à la validation du jeton :

- **Restriction à un groupe** (``MYRAG_GROUPE_EXIGE``). Un jeton valide du realm ne
  suffit pas : il doit porter le groupe demandé dans son claim ``groups``. Sans quoi
  tout compte du realm ministériel entrerait dans une bêta réservée à ses testeurs.
  Vide (défaut) = aucune restriction, comportement d'avant.
- **Identité de l'appelant** (``sub``). Ce claim est la clé du modèle d'accès : c'est
  lui qui garantit à un créateur l'accès à sa collection. Certains realms ne l'émettent
  pas dans le jeton d'ACCÈS (seulement dans le jeton d'identité) ; OpenID Connect
  garantit en revanche que ``/userinfo`` le renvoie toujours. On l'y demande alors,
  et l'identifiant obtenu est le même — ce n'est pas un substitut.
"""

import hashlib
import logging
import time

import httpx
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


def _exiger_le_groupe(claims: dict) -> None:
    """Refuse un jeton qui ne porte pas le groupe demandé par ``MYRAG_GROUPE_EXIGE``.

    Le claim ``groups`` porte le NOM FEUILLE des groupes (mapper Keycloak
    ``full.path=false``), jamais leur chemin : on compare à un nom, pas à un
    « /chemin/groupe ». Panacher les deux formes donnerait un refus systématique
    que rien dans le message ne permettrait d'expliquer.
    """
    exige = settings.myrag_groupe_exige.strip()
    if not exige:
        return
    brut = claims.get("groups", [])
    groupes = brut if isinstance(brut, list) else [brut]
    if exige not in [str(g) for g in groupes]:
        # Tracer le refus sans nommer la personne : le motif suffit au diagnostic.
        logger.warning(
            "Accès refusé : le jeton ne porte pas le groupe requis (%d groupe(s) présent(s))",
            len(groupes),
        )
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux membres du groupe autorisé",
        )


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
    except jwt.PyJWTError:
        # Pas de détail au client (évite de divulguer la raison exacte).
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré")
    except Exception:
        # JWKS injoignable, etc. : on échoue fermé (sécurité), 503 pour
        # distinguer d'un jeton invalide côté exploitation.
        logger.exception("Échec de validation JWT (JWKS injoignable ?)")
        raise HTTPException(status_code=503, detail="Service d'authentification indisponible")

    _exiger_le_groupe(claims)
    return claims


# Liste de dépendances à passer aux routers protégés.
AUTH_REQUIRED = [Depends(verify_jwt)]


# Identifiants résolus par /userinfo, avec une durée de vie courte : on évite un appel
# au fournisseur d'identité à chaque requête sans jamais garder une réponse périmée.
_sub_par_jeton: dict[str, tuple[str, float]] = {}
_SUB_CACHE_TTL = 300.0


async def _sub_depuis_userinfo(jeton: str) -> str | None:
    """Demande le `sub` au point /userinfo du fournisseur.

    Appelé seulement quand le jeton d'accès n'en porte pas. OpenID Connect impose à
    /userinfo de renvoyer `sub` : l'identifiant obtenu est le même que celui du jeton
    d'identité, et il est immuable.
    """
    empreinte = hashlib.sha256(jeton.encode()).hexdigest()
    maintenant = time.time()
    connu = _sub_par_jeton.get(empreinte)
    if connu and connu[1] > maintenant:
        return connu[0]

    url = f"{_issuer()}/protocol/openid-connect/userinfo"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {jeton}"})
        if resp.status_code != 200:
            logger.warning("/userinfo a répondu %s", resp.status_code)
            return None
        sub = resp.json().get("sub")
    except Exception as e:  # noqa: BLE001 — une panne du fournisseur ne doit pas masquer sa cause
        logger.warning("Impossible d'interroger /userinfo : %s", e)
        return None

    if sub:
        if len(_sub_par_jeton) > 2000:
            _sub_par_jeton.clear()
        _sub_par_jeton[empreinte] = (sub, maintenant + _SUB_CACHE_TTL)
    return sub


class CurrentUser:
    """Identité de l'appelant dérivée de l'access token (sub, username, groupes)."""

    __slots__ = ("sub", "username", "groups")

    def __init__(self, sub: str, username: str, groups: list[str]):
        self.sub = sub
        self.username = username
        self.groups = groups


async def current_user(
    claims: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
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

    sub = claims.get("sub", "")
    if not sub and credentials is not None and credentials.credentials:
        # Le jeton d'accès n'a pas d'identité : on la demande au fournisseur. Sans
        # elle, un créateur perdrait l'accès à sa propre collection dès la seconde
        # requête — et rien dans la réponse ne dirait pourquoi.
        sub = await _sub_depuis_userinfo(credentials.credentials) or ""
    if not sub:
        logger.warning(
            "Jeton sans identité exploitable (`sub`). Claims présents : %s",
            ", ".join(sorted(claims.keys())),
        )

    return CurrentUser(
        sub=sub,
        username=claims.get("preferred_username", "") or claims.get("email", ""),
        groups=[g for g in groups if isinstance(g, str)],
    )
