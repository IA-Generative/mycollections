"""Contrôle d'accès aux collections, dérivé des groupes Keycloak.

La visibilité d'une collection est portée par la **convention de nommage** des
groupes MyRAG (pas de colonne en base) :

  - ``<root>/<collection>``        → membre (lecture) ;
  - ``<root>/<collection>-admin``  → administrateur de la collection (écriture) ;
  - ``<root>/superadmin``          → opérateur global (lit et écrit tout).

où ``<root>`` = ``settings.myrag_group_root`` (défaut ``/myrag``). Les groupes
arrivent dans le claim ``groups`` de l'access token (chemins, avec ou sans
slash initial). Tout compte sans groupe MyRAG ne voit aucune collection.
"""

from app.config import settings

SUPERADMIN = "superadmin"
ADMIN_SUFFIX = "-admin"


def _root() -> str:
    return settings.myrag_group_root.rstrip("/")


def _normalise(path: str) -> str:
    """Chemin de groupe normalisé avec un unique slash initial, sans slash final."""
    return "/" + path.strip("/")


def _leaf(path: str) -> str | None:
    """Renvoie le nom de l'enfant direct de <root>, ou None si hors périmètre.

    N'accepte que les enfants directs : ``/myrag/x`` → ``x`` ; ``/myrag`` → None ;
    ``/myrag/x/y`` (imbriqué) → None ; ``/autre/x`` → None.
    """
    prefix = _root() + "/"
    p = _normalise(path)
    if not p.startswith(prefix):
        return None
    leaf = p[len(prefix):]
    if not leaf or "/" in leaf:
        return None
    return leaf


def is_superadmin(groups: list[str] | None) -> bool:
    return any(_leaf(g) == SUPERADMIN for g in (groups or []))


def _collections(groups: list[str] | None, *, admin_only: bool) -> set[str]:
    names: set[str] = set()
    for g in groups or []:
        leaf = _leaf(g)
        if leaf is None or leaf == SUPERADMIN:
            continue
        if leaf.endswith(ADMIN_SUFFIX) and len(leaf) > len(ADMIN_SUFFIX):
            names.add(leaf[: -len(ADMIN_SUFFIX)])
        elif not admin_only:
            names.add(leaf)
    return names


def visible_collection_names(groups: list[str] | None) -> set[str] | None:
    """Noms de collections lisibles. ``None`` = toutes (superadmin)."""
    if is_superadmin(groups):
        return None
    return _collections(groups, admin_only=False)


def writable_collection_names(groups: list[str] | None) -> set[str] | None:
    """Noms de collections modifiables. ``None`` = toutes (superadmin)."""
    if is_superadmin(groups):
        return None
    return _collections(groups, admin_only=True)


def can_read_collection(name: str, groups: list[str] | None) -> bool:
    allowed = visible_collection_names(groups)
    return allowed is None or name in allowed


def can_write_collection(name: str, groups: list[str] | None) -> bool:
    allowed = writable_collection_names(groups)
    return allowed is None or name in allowed


def can_create_collection(groups: list[str] | None) -> bool:
    """Créer une collection est ouvert à tout utilisateur authentifié.

    Créer sa propre collection est une action utilisateur (modèle multi-tenant),
    pas réservée aux opérateurs ; l'endpoint est déjà protégé par l'auth. Seule
    l'administration (sync, jobs, monitoring) reste réservée aux super-admins.
    """
    return True


# ---------------------------------------------------------------------------
# Modèle d'accès complet (par fiche collection)
#
# Les fonctions ci-dessus ne raisonnent que sur la convention de nommage des
# groupes. Celles ci-dessous prennent en compte les attributs portés par la
# fiche collection — ``scope`` (public/group/private), ``scope_groups`` (groupes
# autorisés à interroger) et ``created_by`` (sub du créateur) — et restent
# pures : le routeur charge la fiche et passe ses attributs.
# ---------------------------------------------------------------------------


def groups_match(user_groups: list[str] | None, authorized_paths: list[str] | None) -> bool:
    """Vrai si l'utilisateur appartient à au moins un des groupes autorisés."""
    if not user_groups or not authorized_paths:
        return False
    norm_user = {_normalise(g) for g in user_groups}
    norm_auth = {_normalise(p) for p in authorized_paths}
    return bool(norm_user & norm_auth)


def can_write(
    *,
    name: str,
    created_by: str | None,
    user_groups: list[str] | None,
    user_sub: str | None,
) -> bool:
    """Écriture/gestion : superadmin, créateur, ou membre de ``<name>-admin``.

    Les groupes lecteurs (``scope_groups``) n'accordent **pas** l'écriture.
    """
    if is_superadmin(user_groups):
        return True
    if created_by and user_sub and created_by == user_sub:
        return True
    return can_write_collection(name, user_groups)


def can_read(
    *,
    name: str,
    scope: str | None,
    scope_groups: list[str] | None,
    created_by: str | None,
    user_groups: list[str] | None,
    user_sub: str | None,
) -> bool:
    """Lecture/interrogation, selon la portée de la collection.

    - les gestionnaires (créateur, ``<name>-admin``, superadmin) lisent toujours ;
    - ``public``  → tout utilisateur authentifié ;
    - ``private`` → gestionnaires uniquement ;
    - ``group``   → membre de ``/myrag/<name>[-admin]`` **ou** d'un groupe autorisé.
    """
    if can_write(name=name, created_by=created_by, user_groups=user_groups, user_sub=user_sub):
        return True
    if scope == "public":
        return True
    if scope == "private":
        return False
    # scope == "group" (défaut)
    return can_read_collection(name, user_groups) or groups_match(user_groups, scope_groups)
