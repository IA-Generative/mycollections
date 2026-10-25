"""Les documents écartés d'un import Résana : pourquoi, en mots simples, et quoi faire.

Un écart porte un `code` stable (le texte de la raison peut changer, le code non) ; `EXPLICATIONS`
dit à l'écran et dans l'export ce que le code signifie et ce que la personne peut faire. `coder`
retrouve le code d'un écart noté avant que le code existe, à partir du texte de sa raison.
Module pur : aucune entrée-sortie.
"""

from __future__ import annotations

import csv
import io

#: code → (libellé court, explication, quoi faire). L'ordre est celui de l'affichage.
EXPLICATIONS: dict[str, tuple[str, str, str]] = {
    "hors_droits": (
        "Résana vous refuse ce document",
        "Mes collections lit Résana avec vos droits : ce document ne vous est pas ouvert dans Résana.",
        "Demandez l'accès à l'administrateur de l'espace, puis « Mettre à jour » : le document sera repris.",
    ),
    "introuvable": (
        "Introuvable dans Résana",
        "Le document figurait dans la liste du dossier, mais Résana ne le sert plus (déplacé ou supprimé entre-temps).",
        "Rien à faire : « Mettre à jour » relira la liste.",
    ),
    "trop_volumineux": (
        "Trop volumineux",
        "Le document dépasse la taille que Résana ou l'indexation admettent.",
        "Déposez dans Résana une version plus légère (sans images lourdes, ou découpée).",
    ),
    "format": (
        "Format non pris en charge",
        "Le moteur de recherche ne sait pas lire ce type de fichier (archive, message, exécutable…).",
        "Déposez dans Résana une version en PDF, Word, LibreOffice ou texte.",
    ),
    "conversion": (
        "Conversion en PDF impossible",
        "Le fichier bureautique n'a pas pu être converti pour l'indexation (fichier abîmé ou protégé).",
        "Rouvrez-le, enregistrez-le de nouveau (ou exportez-le en PDF) dans Résana.",
    ),
    "illisible": (
        "Texte illisible",
        "Le fichier n'a pas de texte exploitable : encodage inconnu ou contenu binaire.",
        "Déposez dans Résana une version électronique lisible (pas une image du texte).",
    ),
    "vide": (
        "Document vide",
        "Le fichier ne contient aucun texte.",
        "Vérifiez le fichier dans Résana ; s'il est vide, retirez-le du dossier.",
    ),
    "doublon": (
        "Même contenu qu'un autre document",
        "Son contenu est identique à un document déjà indexé : une seule copie suffit aux réponses.",
        "Rien à faire. Si les deux doivent être cités séparément, gardez une version qui diffère.",
    ),
    "autre": (
        "Écarté",
        "Le service Résana a refusé ce document pour une raison inattendue.",
        "Réessayez avec « Mettre à jour » ; si l'écart persiste, signalez-le.",
    ),
}

#: Début du texte de la raison → code, pour les écarts notés avant le code (et pour les raisons
#: construites à la volée). Testé du plus précis au plus général.
_PAR_TEXTE: tuple[tuple[str, str], ...] = (
    ("Résana vous refuse", "hors_droits"),
    ("introuvable", "introuvable"),
    ("trop volumineux", "trop_volumineux"),
    ("dépasse la taille", "trop_volumineux"),
    ("format non pris en charge", "format"),
    ("conversion en PDF impossible", "conversion"),
    ("texte illisible", "illisible"),
    ("document vide", "vide"),
    ("même contenu", "doublon"),
)


def coder(raison: str | None, code: str | None = None) -> str:
    """Le code d'un écart : celui noté s'il est connu, sinon déduit du texte, sinon `autre`."""
    if code in EXPLICATIONS:
        return code
    texte = (raison or "").lower()
    for debut, c in _PAR_TEXTE:
        if debut.lower() in texte:
            return c
    return "autre"


def code_erreur_resana(code_service: str) -> str:
    """Le code d'écart d'une erreur du service d'export (403 hors_droits, 404 introuvable…)."""
    return code_service if code_service in EXPLICATIONS else "autre"


def expliquer(code: str) -> dict:
    code = code if code in EXPLICATIONS else "autre"
    libelle, explication, quoi_faire = EXPLICATIONS[code]
    return {"code": code, "libelle": libelle, "explication": explication, "quoi_faire": quoi_faire}


def cellule(v) -> str:
    """Un tableur exécuterait une cellule qui commence par = + - @ : on la neutralise."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


COLONNES_CSV = ("titre", "dossier", "raison", "explication", "quoi_faire", "meme_contenu_que", "adresse_resana")


def vers_csv(ecartes: list[dict]) -> str:
    """Les écartés pour un tableur : UTF-8 avec BOM, `;`, une ligne par document."""
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    w.writerow(COLONNES_CSV)
    for e in ecartes:
        ex = expliquer(coder(e.get("raison"), e.get("code")))
        w.writerow(
            [
                cellule(e.get("titre")),
                cellule(e.get("chemin")),
                cellule(e.get("raison") or ex["libelle"]),
                cellule(ex["explication"]),
                cellule(ex["quoi_faire"]),
                cellule(e.get("doublon_de_titre")),
                cellule(e.get("url")),
            ]
        )
    return "﻿" + tampon.getvalue()
