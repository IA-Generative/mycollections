"""Ce que le service sait faire — lu chez le menu commun, une seule source de vérité.

`capacites.json` vit dans le dépôt mirai-apps-menu et se règle sans reconstruire
d'image. L'écran le lit en même origine (`/_beta/capacites.json`) ; le serveur le lit
par le service interne du cluster, avec un cache court et un repli : la dernière
valeur connue, sinon des défauts qui n'affichent rien et n'écrivent rien.

Un drapeau à `false` ne se contente pas de cacher un bouton : la route répond 404.

Drapeaux : `demandes`, `signalements` (le collectif), `assistants`, `entraide` (ADR-0003), `resana`
(import d'un dossier Résana, docs/resana.md).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("myrag.capacites")

DELAI_S = 2.0
CACHE_S = 60.0
DRAPEAUX = ("demandes", "signalements", "assistants", "entraide", "resana")

_cache: dict = {"valeur": None, "expire": 0.0}


def _defauts() -> dict:
    return {**dict.fromkeys(DRAPEAUX, False), "seuil_chantier": int(settings.seuil_chantier_defaut)}


def _normaliser(brut: dict, valeur: dict | None = None) -> dict:
    valeur = dict(valeur) if valeur is not None else _defauts()
    for nom in DRAPEAUX:
        if nom in brut:
            valeur[nom] = brut[nom] is True  # jamais « truthy », comme le menu
    seuil = brut.get("seuil_chantier")
    if isinstance(seuil, int) and not isinstance(seuil, bool) and 1 <= seuil <= 1000:
        valeur["seuil_chantier"] = seuil
    return valeur


def _surcharger(valeur: dict) -> dict:
    """La surcharge de l'environnement (MYCOLLECTIONS_CAPACITES_SURCHARGE, un objet JSON), posée
    par-dessus ce que dit le menu : une prévisualisation ou un poste de développement allume une
    fonction sans toucher au capacites.json partagé. Illisible : ignorée, avec un avertissement."""
    brut = (settings.capacites_surcharge or "").strip()
    if not brut:
        return valeur
    try:
        surcharge = json.loads(brut)
        if not isinstance(surcharge, dict):
            raise ValueError("ce n'est pas un objet")
    except ValueError as e:
        logger.warning("MYCOLLECTIONS_CAPACITES_SURCHARGE illisible (%s) : ignorée", e)
        return valeur
    return _normaliser(surcharge, valeur)


def _lire_depuis_le_menu() -> dict:
    """Les capacités en vigueur. Ne bloque jamais plus de DELAI_S, ne lève jamais."""
    return _surcharger(_lire_le_menu())


def _lire_le_menu() -> dict:
    if not settings.capacites_url:
        return _defauts()
    maintenant = time.monotonic()
    if _cache["valeur"] is not None and maintenant < _cache["expire"]:
        return dict(_cache["valeur"])
    try:
        reponse = httpx.get(settings.capacites_url, timeout=DELAI_S)
        reponse.raise_for_status()
        brut = reponse.json()
        if not isinstance(brut, dict):
            raise ValueError("capacites.json n'est pas un objet")
        _cache["valeur"] = _normaliser(brut)
        _cache["expire"] = maintenant + CACHE_S
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("capacites.json illisible (%s) : dernière valeur connue ou défauts", e)
        if _cache["valeur"] is None:
            return _defauts()
    return dict(_cache["valeur"])


# Le point d'appel des routes — et la couture que les tests remplacent. Les tests du
# lecteur lui-même appellent `_lire_depuis_le_menu`.
lire = _lire_depuis_le_menu


async def lire_async() -> dict:
    """La même lecture, hors de la boucle d'événements : un menu lent ne fige pas l'API."""
    return await asyncio.to_thread(lambda: lire())


def oublier() -> None:
    _cache["valeur"] = None
    _cache["expire"] = 0.0


def seuil_chantier() -> int:
    return int(lire()["seuil_chantier"])


def activee(nom: str) -> bool:
    return lire().get(nom) is True
