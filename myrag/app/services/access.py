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
    """Créer une collection = action d'opérateur : superadmin, ou admin d'au
    moins une collection. Un simple membre (lecture) ou un auditeur ne peut pas.
    """
    if is_superadmin(groups):
        return True
    return bool(_collections(groups, admin_only=True))
