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

from app.config import settings

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

#: Les tableurs, que l'indexeur ne lit qu'avec son lecteur `spreadsheet` (openrag#15) : documents
#: seulement si `indexeur_lit_tableurs`, sinon convertis en PDF (ou écartés).
FORMATS_TABLEUR = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xls": "application/vnd.ms-excel",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}


def formats_document() -> dict[str, str]:
    """Extension → type MIME de ce que l'indexeur lit, tableurs compris s'il sait les lire."""
    return {**FORMATS_DOCUMENT, **FORMATS_TABLEUR} if settings.indexeur_lit_tableurs else FORMATS_DOCUMENT


#: Les premiers octets attendus de chaque document (un .docx/.pptx est une archive zip).
_SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".doc": (b"\xd0\xcf\x11\xe0",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".xlsx": (b"PK\x03\x04",),
    ".xlsm": (b"PK\x03\x04",),
    ".ods": (b"PK\x03\x04",),
    ".xls": (b"\xd0\xcf\x11\xe0",),
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
    if ext in formats_document():
        signatures = _SIGNATURES.get(ext)
        if signatures and not tete.startswith(signatures):
            return None  # l'extension ment : on ne confie pas à OpenRAG un fichier qu'il lirait mal
        return Nature.DOCUMENT
    if tete.startswith(_BINAIRES) or b"\x00" in tete:
        return None  # un binaire sans extension connue (ou renommé en .md)
    return Nature.TEXTE


#: Les fichiers texte que l'indexeur lit sous leur propre nom. Les autres (.csv, .json, .xml…) partent
#: sous un nom en `.txt` : l'indexeur choisit son lecteur à l'extension et les refusait (parcours e2e
#: des formats, 2026-10-26).
TEXTE_LU_PAR_L_INDEXEUR = (".txt", ".md", ".markdown")


def nom_pour_l_indexeur(nom: str) -> str:
    """Le nom sous lequel un fichier part vers l'indexeur : le sien, sauf un texte qu'il ne lirait pas
    sous ce nom (`format.csv` → `format.csv.txt`). Un document (PDF, Word…) garde son nom."""
    ext = extension(nom)
    if ext in formats_document() or ext in TEXTE_LU_PAR_L_INDEXEUR:
        return nom
    return f"{nom}.txt"


def type_mime(nom: str) -> str:
    return formats_document().get(extension(nom), "application/octet-stream")


#: En dessous de ce nombre moyen de caractères par page, un PDF est tenu pour un scan : une image de
#: chaque page, sans couche texte. Quelques caractères suffisent à un tampon ou à un numéro de page.
SCAN_CARACTERES_PAR_PAGE = 30
#: Pages examinées au plus : la nature d'un PDF se voit dès ses premières pages.
SCAN_PAGES_EXAMINEES = 10


def est_un_scan(nom: str, contenu: bytes) -> bool:
    """Un PDF sans texte lisible : une numérisation de copieur, le plus souvent. L'indexeur ne le
    lit qu'avec la reconnaissance de caractères (OCR) ; mieux vaut, quand elle existe, sa version
    électronique. Un PDF illisible ici n'est pas déclaré scan : l'indexeur dira ce qu'il en est."""
    if extension(nom) != ".pdf" or not contenu.startswith(b"%PDF"):
        return False
    import io
    import logging

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        lecteur = PdfReader(io.BytesIO(contenu))
        pages = lecteur.pages[:SCAN_PAGES_EXAMINEES]
        if not pages:
            return False
        caracteres = sum(len((p.extract_text() or "").strip()) for p in pages)
    except Exception:  # noqa: BLE001 — chiffré, abîmé : on ne conclut pas
        return False
    return caracteres < SCAN_CARACTERES_PAR_PAGE * len(pages)
