"""Ce qu'on sait confier à OpenRAG, et ce qu'on sait lire localement.

Tout fichier accepté au dépôt part ENTIER vers OpenRAG, qui le lit et le découpe
lui-même (découpage d'indexation — ADR-0005). Avant : les textes étaient découpés
ici, selon une stratégie, et les documents partaient tels quels ; le chunker
d'OpenRAG (`structured_section`) couvre les mêmes besoins — articles de code
atomiques, découpe sur les titres, chemin d'en-tête préfixé à chaque passage.

Le CSV et l'extension .markdown ne sont pas dans les loaders d'OpenRAG : refusés
au dépôt. Le texte reste lisible localement pour la structuration (graphe de
références) : c'est le rôle de FORMATS_TEXTE.

Les formats de document sont ceux qu'OpenRAG déclare (`loader.mimetypes` de sa
configuration). La nature se décide sur l'extension ET les premiers octets : un
PDF renommé en .md n'est pas du texte.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath

#: Le texte lisible localement — découpable ici pour la structuration (graphe).
#: (.csv et .markdown y figurent bien qu'OpenRAG ne les accepte pas au dépôt.)
FORMATS_TEXTE = (".txt", ".md", ".markdown", ".csv")


class Nature(StrEnum):
    """Ce qu'on sait faire d'un fichier : le confier entier à OpenRAG (DOCUMENT),
    ou le lire comme texte localement (TEXTE — structuration du graphe ; OpenRAG
    ne l'accepte pas au dépôt : .csv, .markdown, extension inconnue)."""

    TEXTE = "texte"
    DOCUMENT = "document"


#: Extension → type MIME annoncé à OpenRAG. Tout fichier accepté au dépôt part
#: entier : c'est OpenRAG qui le découpe (ADR-0005).
FORMATS_DOCUMENT = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".eml": "message/rfc822",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

#: Les premiers octets attendus de chaque document binaire (un .docx/.pptx est une archive zip).
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

ACCEPTES = tuple(FORMATS_DOCUMENT)

MESSAGE_FORMAT = "Ce format n'est pas pris en charge. Formats acceptés : texte (.txt, .md), PDF, Word (.docx, .doc), PowerPoint (.pptx), courriel (.eml) et images (.png, .jpg). Le CSV n'est pas lu : convertissez-le en .txt ou .md."


def extension(nom: str) -> str:
    return PurePosixPath((nom or "").replace("\\", "/")).suffix.lower()


def nature(nom: str, contenu: bytes) -> Nature | None:
    """La nature du fichier, ou None (format refusé).

    DOCUMENT : confiable entier à OpenRAG (extension connue, octets d'accord).
    TEXTE : lisible localement (structuration du graphe) mais pas confiable —
    OpenRAG n'a pas de loader (.csv, .markdown) ou l'extension est inconnue.
    """
    ext = extension(nom)
    tete = contenu[:4096]
    binaire = tete.startswith(_BINAIRES) or b"\x00" in tete
    if ext in FORMATS_DOCUMENT:
        signatures = _SIGNATURES.get(ext)
        if signatures and not tete.startswith(signatures):
            return None  # l'extension ment : on ne confie pas à OpenRAG un fichier qu'il lirait mal
        if ext in FORMATS_TEXTE and binaire:
            return None  # un binaire renommé en .txt ou .md
        return Nature.DOCUMENT
    if binaire:
        return None  # un binaire sans extension connue
    return Nature.TEXTE


def type_mime(nom: str) -> str:
    return FORMATS_DOCUMENT.get(extension(nom), "application/octet-stream")
