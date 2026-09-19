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
