"""Lire un CSV de data.gouv.fr sans se tromper d'encodage ni de séparateur, et
convertir des nombres écrits à la française (« 1 786 », « 0,0078 »)."""

from __future__ import annotations

import csv
import io
import re
import unicodedata

_ESPACES = re.compile(r"[\s  ?]")


def decoder(octets: bytes) -> str:
    """UTF-8 (avec ou sans BOM) d'abord ; sinon cp850 (la liste NATINF est écrite en
    DOS : é = 0x82) ou cp1252 (SSMSI, SIS : é = 0xE9) — on regarde quels octets sont là."""
    try:
        return octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    echantillon = octets[:200000]
    cp1252 = sum(echantillon.count(b) for b in (b"\xe9", b"\xe8", b"\xe0", b"\xea"))
    cp850 = sum(echantillon.count(b) for b in (b"\x82", b"\x8a", b"\x85", b"\x88"))
    for encodage in (("cp850", "cp1252") if cp850 > cp1252 else ("cp1252", "cp850")):
        try:
            return octets.decode(encodage)
        except UnicodeDecodeError:
            continue
    return octets.decode("latin-1")


def lire_csv(octets: bytes, separateur: str | None = None) -> list[dict]:
    texte = decoder(octets)
    premiere = texte.split("\n", 1)[0]
    if separateur is None:
        separateur = ";" if premiere.count(";") >= premiere.count(",") else ","
    lecteur = csv.DictReader(io.StringIO(texte), delimiter=separateur)
    lignes = []
    for ligne in lecteur:
        lignes.append({(k or "").strip().lstrip("﻿"): (v or "").strip() for k, v in ligne.items() if k is not None})
    return lignes


def nombre(valeur: str | None) -> float | None:
    """« 1 786 » → 1786, « 0,0078 » → 0.0078, vide → None."""
    if valeur is None:
        return None
    v = _ESPACES.sub("", str(valeur)).replace(",", ".")
    if v in ("", "-", "NA", "ND", "nd", "s"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def entier(valeur: str | None) -> int:
    n = nombre(valeur)
    return int(n) if n is not None else 0


def fmt(n: float | int | None, decimales: int = 0) -> str:
    if n is None:
        return "—"
    if decimales == 0:
        return f"{int(round(n)):,}".replace(",", " ")
    return f"{n:.{decimales}f}".replace(".", ",")


def colonne(ligne: dict, *candidates: str) -> str:
    """La première colonne présente parmi des noms possibles (les en-têtes varient d'un millésime à l'autre)."""
    for c in candidates:
        if c in ligne:
            return ligne[c]
    def _plat(t: str) -> str:
        return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()
    plats = {_plat(k): v for k, v in ligne.items()}
    for c in candidates:
        if _plat(c) in plats:
            return plats[_plat(c)]
    return ""
