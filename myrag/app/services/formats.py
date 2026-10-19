"""Ce qu'on sait indexer, et par quel chemin.

Deux chemins :

- le TEXTE (.txt, .md, .csv) est découpé ici, selon la stratégie choisie (article, section,
  question-réponse…), puis chaque passage part vers OpenRAG ;
- les DOCUMENTS (PDF, Word, PowerPoint, courriels, images) partent tels quels vers OpenRAG, qui
  sait les lire (texte, tableaux, OCR, légende des images) et les découpe lui-même. Avant : on les
  décodait comme du texte et ils partaient indexés en caractères illisibles (diagnostic d'octobre
  2026), d'où un refus pur et simple ; OpenRAG les lit mieux que nous ne le ferions.

Les formats de document sont ceux qu'OpenRAG déclare (`loader.mimetypes` de sa configuration).
La nature se décide sur l'extension ET les premiers octets : un PDF renommé en .md n'est pas du texte.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath

FORMATS_TEXTE = (".txt", ".md", ".markdown", ".csv")


class Nature(StrEnum):
    """Ce qu'on sait faire d'un fichier : le découper ici, ou le confier à OpenRAG."""

    TEXTE = "texte"
    DOCUMENT = "document"


#: Extension → type MIME annoncé à OpenRAG.
FORMATS_DOCUMENT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".eml": "message/rfc822",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

#: Les premiers octets attendus de chaque document (un .docx/.pptx est une archive zip).
_SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".doc": (b"\xd0\xcf\x11\xe0",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}

_BINAIRES = (b"%PDF", b"PK\x03\x04", b"\xd0\xcf\x11\xe0", b"\x89PNG", b"\xff\xd8\xff", b"GIF8")

ACCEPTES = FORMATS_TEXTE + tuple(FORMATS_DOCUMENT)

MESSAGE_FORMAT = (
    "Ce format n'est pas pris en charge. Formats acceptés : texte (.txt, .md, .csv), PDF, Word (.docx, .doc), PowerPoint (.pptx), courriel (.eml) et images (.png, .jpg)."
)


def extension(nom: str) -> str:
    return PurePosixPath((nom or "").replace("\\", "/")).suffix.lower()


def nature(nom: str, contenu: bytes) -> Nature | None:
    """La nature du fichier, ou None (format refusé)."""
    ext = extension(nom)
    tete = contenu[:4096]
    if ext in FORMATS_DOCUMENT:
        signatures = _SIGNATURES.get(ext)
        if signatures and not tete.startswith(signatures):
            return None  # l'extension ment : on ne confie pas à OpenRAG un fichier qu'il lirait mal
        return Nature.DOCUMENT
    if tete.startswith(_BINAIRES) or b"\x00" in tete:
        return None  # un binaire sans extension connue (ou renommé en .md)
    return Nature.TEXTE


def type_mime(nom: str) -> str:
    return FORMATS_DOCUMENT.get(extension(nom), "application/octet-stream")
