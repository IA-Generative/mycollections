"""Convertir en PDF les formats bureautiques que l'indexeur ne lit pas (#146).

L'administration produit beaucoup en LibreOffice (`.odt`, `.odp`, `.ods`) et garde d'anciens
fichiers Office (`.ppt`, `.xls`), que l'indexeur ne lit pas. Un service à part, Gotenberg (route
LibreOffice), les convertit en PDF avant l'envoi. Il tourne dans son propre pod : l'image du
backend reste légère, et le service peut servir à d'autres applications.

Sans service configuré (`MYCOLLECTIONS_CONVERSION_URL` vide), rien ne change : ces formats restent
écartés. Une conversion à la fois, dans un délai borné : le service n'est pas noyé pendant un
grand import.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.services import formats

logger = logging.getLogger(__name__)

#: Les formats confiés au service de conversion (ceux que l'indexeur lit déjà n'y passent pas).
FORMATS_CONVERTIBLES = (".odt", ".odp", ".ods", ".rtf", ".ppt", ".pps", ".xls", ".xlsx", ".xlsm", ".fodt", ".fods", ".fodp")
#: La route LibreOffice de Gotenberg.
ROUTE = "/forms/libreoffice/convert"

_UNE_A_LA_FOIS = asyncio.Semaphore(1)


class ConversionImpossible(Exception):
    """Le service n'a pas converti le fichier (absent, délai dépassé, fichier abîmé)."""


def active() -> bool:
    return bool(settings.conversion_url)


def convertible(nom: str) -> bool:
    return formats.extension(nom) in FORMATS_CONVERTIBLES


def nom_pdf(nom: str) -> str:
    """« budget.ods » ⇒ « budget (ods).pdf » : le format d'origine reste lisible, et le nom ne se
    confond pas avec un « budget.pdf » voisin."""
    ext = formats.extension(nom)
    base = nom[: -len(ext)] if ext else nom
    return f"{base} ({ext.lstrip('.')}).pdf" if ext else f"{nom}.pdf"


async def en_pdf(nom: str, contenu: bytes) -> bytes:
    """Le PDF du fichier, rendu par le service de conversion. Lève `ConversionImpossible`."""
    if not active():
        raise ConversionImpossible("service de conversion non configuré")
    url = settings.conversion_url.rstrip("/") + ROUTE
    async with _UNE_A_LA_FOIS:
        try:
            async with httpx.AsyncClient(timeout=settings.conversion_delai_s) as client:
                r = await client.post(url, files={"files": (nom, contenu)})
        except httpx.HTTPError as e:
            raise ConversionImpossible(f"service injoignable ({type(e).__name__})") from None
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        logger.warning("conversion de « %s » refusée : %s", nom, r.status_code)
        raise ConversionImpossible(f"le service a répondu {r.status_code}")
    return r.content
