"""Nommer une collection : le TITRE que lit une personne, distinct de l'identifiant
que tapent les applications (`openrag-<name>`).

Fonctions pures — la reprise des collections existantes (database._retro_remplir_titres)
et le catalogue s'en servent.
"""

from __future__ import annotations

import re

#: Préfixes de PROVENANCE : ils disent d'où vient la collection, pas ce qu'elle contient.
PREFIXES_DE_PROVENANCE = ("demo-", "amorce-", "rag-", "test-")

#: Sigles à rendre en capitales quand le titre est déduit de l'identifiant.
SIGLES = {
    "ceseda", "dgef", "faq", "sdis", "baac", "natinf", "ssmsi", "rne", "sdst", "anef",
    "ta", "caa", "cnda", "cedh", "rh", "si", "pdf", "md",
}

_MARQUES = ("📚", "📖")
_PREFIXES_D_ALIAS = ("MirAI ", "Mirai RAG — ", "Mirai RAG - ")
_SUFFIXES_D_ALIAS = (" (partagé)", " (corpus partagé)")


def titre_depuis_nom(name: str) -> str:
    """`amorce-ta-caa-ceseda` → « TA CAA CESEDA ». Dernier recours : mieux vaut un
    titre saisi ; celui-ci évite seulement d'afficher l'identifiant brut."""
    n = (name or "").strip().lower()
    for p in PREFIXES_DE_PROVENANCE:
        if n.startswith(p) and len(n) > len(p):
            n = n[len(p):]
            break
    mots = [m for m in re.split(r"[-_.\s]+", n) if m]
    if not mots:
        return name or ""
    rendus = [m.upper() if m in SIGLES else m for m in mots]
    if rendus[0] == mots[0] and mots[0] not in SIGLES:
        rendus[0] = mots[0][:1].upper() + mots[0][1:]
    return " ".join(rendus)


def titre_depuis_alias(alias: str | None, name: str = "") -> str:
    """Le nom posé à la publication, débarrassé de ses marques. Vide si l'alias
    n'était qu'un identifiant déguisé (`📚 demo-x`, `openrag-x`, `MirAI demo-x`)."""
    a = (alias or "").strip()
    for m in _MARQUES:
        a = a.replace(m, "")
    a = a.strip()
    for p in _PREFIXES_D_ALIAS:
        if a.startswith(p):
            a = a[len(p):].strip()
    for s in _SUFFIXES_D_ALIAS:
        if a.endswith(s):
            a = a[: -len(s)].strip()
    if not a or a.lower().startswith("openrag-") or (name and a.lower() == name.lower()):
        return ""
    return a[:255]


def titre_de(collection: dict) -> str:
    """Le titre à montrer : celui de la fiche, sinon déduit du nom."""
    return (collection.get("titre") or "").strip() or titre_depuis_nom(collection.get("name", ""))


_CLE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def cle_valide(cle: str) -> bool:
    return bool(_CLE_RE.match(cle or "")) and len(cle) <= 64


# ─── L'identifiant : ce que tapent les applications ───────────────────────────────────

IDENT_MIN, IDENT_MAX = 3, 40
_IDENT_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

#: Segments de route (`/api/collections/<x>`) et dossiers du volume : jamais un identifiant.
#: `all` et `default` sont des modèles d'OpenRAG (`openrag-all`).
RESERVES = frozenset({"all", "default", "alias", "check-name", "regles-nommage", "templates"})

_MOTS_VIDES = frozenset({"le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "et", "ou", "a", "au", "aux",
                         "en", "sur", "pour", "par", "dans"})

MOTIFS = {
    "empty": "Donnez un identifiant.",
    "longueur": f"Entre {IDENT_MIN} et {IDENT_MAX} caractères.",
    "format": "Minuscules, chiffres et tirets seulement, en commençant par une lettre (ex. codes-natinf).",
    "prefixe": "Ce préfixe dit d'où vient la collection, pas ce qu'elle contient : nommez-la par son contenu.",
    "reserve": "Ce mot est réservé par l'application.",
    "db": "Cet identifiant est déjà pris.",
    "partition": "Cet identifiant est déjà pris (une partition porte ce nom).",
}


def prefixes_bannis() -> tuple[str, ...]:
    from app.config import settings
    return tuple(p.strip().lower() for p in settings.myrag_prefixes_bannis.split(",") if p.strip())


def motif_de_refus(identifiant: str) -> str | None:
    """None si l'identifiant (déjà normalisé) est acceptable ; sinon la clé de MOTIFS."""
    n = identifiant or ""
    if not n:
        return "empty"
    if not IDENT_MIN <= len(n) <= IDENT_MAX:
        return "longueur"
    if not _IDENT_RE.match(n):
        return "format"
    if n in RESERVES:
        return "reserve"
    if any(n.startswith(p) for p in prefixes_bannis()):
        return "prefixe"
    return None


def _sans_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def deriver_identifiant(titre: str) -> str:
    """« Codes NATINF » → `codes-natinf` ; « Droit des étrangers » → `droit-etrangers`.
    Translittère (é → e) au lieu de supprimer, retire les mots vides, coupe sur un tiret."""
    mots = [m for m in re.split(r"[^a-z0-9]+", _sans_accents(titre or "").lower()) if m]
    utiles = [m for m in mots if m not in _MOTS_VIDES] or mots
    ident = "-".join(utiles)
    ident = re.sub(r"^[0-9-]+", "", ident)
    if len(ident) > IDENT_MAX:
        ident = ident[:IDENT_MAX + 1].rsplit("-", 1)[0] if "-" in ident[:IDENT_MAX + 1] else ident[:IDENT_MAX]
    return ident.strip("-")


def regles() -> dict:
    """Ce que le formulaire de création doit savoir — servi tel quel au front."""
    return {"min": IDENT_MIN, "max": IDENT_MAX, "prefixes_bannis": list(prefixes_bannis()),
            "reserves": sorted(RESERVES), "motifs": MOTIFS}
