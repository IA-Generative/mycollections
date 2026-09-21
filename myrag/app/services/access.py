"""Contrôle d'accès aux collections, dérivé des groupes Keycloak.

La visibilité d'une collection est portée par la **convention de nommage** des
groupes MyRAG (pas de colonne en base) :

  - ``<root>/<collection>``        → membre (lecture) ;
  - ``<root>/<collection>-admin``  → administrateur de la collection (écriture) ;
  - ``<root>/superadmin``          → opérateur global (lit et écrit tout).

où ``<root>`` = ``settings.myrag_group_root`` (défaut ``/myrag``). Les groupes
arrivent dans le claim ``groups`` de l'access token. Tout compte sans groupe
MyRAG ne voit aucune collection.

**Seuls des chemins complets donnent des droits** (mapper Keycloak
``full.path=true``). Un nom court n'est pas unique dans un realm, et dans un
realm où les utilisateurs créent eux-mêmes leurs groupes (keycloak-comu, sous
``/g``) il est à la portée de n'importe qui : reconnaître ``superadmin``, ou un
nom qui *ressemble* à un chemin (``myrag/superadmin`` — Keycloak accepte la barre
oblique dans un nom), serait une élévation de privilèges. Un claim qui porte ne
serait-ce qu'une valeur sans ``/`` initial est donc en noms courts : on n'en tire
AUCUN droit (cf. ``chemins``).
"""

import logging

from app.config import settings

logger = logging.getLogger("myrag.access")

SUPERADMIN = "superadmin"
ADMIN_SUFFIX = "-admin"


def _root() -> str:
    return settings.myrag_group_root.rstrip("/")


def _normalise(path: str) -> str:
    """Chemin de groupe normalisé avec un unique slash initial, sans slash final."""
    return "/" + path.strip("/")


_noms_courts_signales = False


def chemins(groups: list[str] | None) -> list[str]:
    """Les groupes du claim s'il est en chemins complets, sinon une liste vide.

    Keycloak en ``full.path=true`` émet TOUJOURS un ``/`` initial. Une seule valeur
    sans lui trahit un mapper en ``full.path=false`` : toutes les valeurs sont alors
    des noms courts, y compris celles qui commencent par ``/`` (un groupe peut
    s'appeler ``/myrag/superadmin``). On ne peut pas les distinguer d'un chemin :
    on les écarte toutes. En bêta, le groupe exigé (``MYRAG_GROUPE_EXIGE``) garantit
    qu'un claim en noms courts porte au moins une valeur sans ``/``.
    """
    global _noms_courts_signales
    valeurs = [g for g in groups or [] if isinstance(g, str)]
    if any(not g.startswith("/") for g in valeurs):
        if not _noms_courts_signales:
            _noms_courts_signales = True
            logger.warning(
                "Claim `groups` en noms courts (mapper full.path=false) : aucun droit "
                "n'en est tiré — superadmin et groupes de collection restent inopérants"
            )
        return []
    return valeurs


def _leaf(path: str) -> str | None:
    """Renvoie le nom de l'enfant direct de <root>, ou None si hors périmètre.

    N'accepte que les enfants directs : ``/myrag/x`` → ``x`` ; ``/myrag`` → None ;
    ``/myrag/x/y`` (imbriqué) → None ; ``/autre/x`` → None. Reçoit un chemin
    complet (cf. ``chemins``).
    """
    prefix = _root() + "/"
    p = path.rstrip("/")
    if not p.startswith(prefix):
        return None
    leaf = p[len(prefix):]
    if not leaf or "/" in leaf:
        return None
    return leaf


def is_superadmin(groups: list[str] | None) -> bool:
    return any(_leaf(g) == SUPERADMIN for g in chemins(groups))


def _collections(groups: list[str] | None, *, admin_only: bool) -> set[str]:
    names: set[str] = set()
    for g in chemins(groups):
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
    """Vrai si l'utilisateur appartient à au moins un des groupes autorisés.

    Comparaison de chemins complets : côté utilisateur, un claim en noms courts ne
    correspond à rien (cf. ``chemins``) ; côté fiche, un nom court enregistré du
    temps du mapper ``full.path=false`` ne désigne plus aucun groupe.
    """
    user_paths = chemins(user_groups)
    if not user_paths or not authorized_paths:
        return False
    norm_user = {_normalise(g) for g in user_paths}
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
