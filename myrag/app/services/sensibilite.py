"""Le plafond de sensibilité : une seule règle, celle de « pas d'écriture vers le bas ».

Les niveaux (`chunker.Sensitivity`) forment une échelle, du moins protégé au plus protégé. Un
contenant ne reçoit que du contenu de niveau inférieur ou égal à son plafond :

- **une collection ne descend pas sous ses sources** : importée d'une instance de Fichiers dont
  les documents sont réputés au niveau `sensibilite_max` de l'instance, elle est au moins à ce
  niveau ; elle peut monter ;
- **une destination a un plafond** (`MYCOLLECTIONS_DESTINATIONS_SENSIBILITE_MAX`) : une collection
  au-dessus n'y va pas (une collection « Données personnelles » ne part pas dans un chat réglé à
  « Interne »).

Ainsi, une collection destinée à « Public — internet » ne reçoit que du public. L'ordre total est un
choix prudent (toujours vers le plus protecteur), le même que celui de la migration qui range les
anciennes valeurs `confidential` et `secret` en `restricted`. Module pur, sans entrée-sortie, hors la
lecture du réglage des destinations. Voir docs/fichiers.md.
"""

from __future__ import annotations

import json
import logging

from app.services.chunker import LIBELLES_SENSIBILITE, Sensitivity

logger = logging.getLogger(__name__)

#: Du moins protégé au plus protégé.
ECHELLE: tuple[Sensitivity, ...] = (
    Sensitivity.PUBLIC,
    Sensitivity.INTERNAL,
    Sensitivity.PERSONAL,
    Sensitivity.PERSONAL_SENSITIVE,
    Sensitivity.CONTROLLED,
    Sensitivity.RESTRICTED,
)

#: Les destinations qui ont un plafond réglable.
DESTINATIONS = ("chat", "recherche", "navigateur")
LIBELLES_DESTINATION = {"chat": "le chat MirAI", "recherche": "la recherche de Mon portail", "navigateur": "l'extension navigateur"}


def niveau(valeur: str | Sensitivity | None, defaut: Sensitivity = Sensitivity.INTERNAL) -> Sensitivity:
    """Le niveau d'une valeur (une ancienne valeur donne sa nouvelle) ; une valeur inconnue donne
    `defaut`."""
    try:
        return Sensitivity(valeur) if valeur else defaut
    except ValueError:
        return defaut


def rang(valeur: str | Sensitivity) -> int:
    return ECHELLE.index(niveau(valeur, Sensitivity.RESTRICTED))


def compatible(contenu: str | Sensitivity, plafond: str | Sensitivity) -> bool:
    """Un contenu de ce niveau peut-il entrer sous ce plafond ?"""
    return rang(contenu) <= rang(plafond)


def libelle(valeur: str | Sensitivity) -> str:
    return LIBELLES_SENSIBILITE.get(niveau(valeur).value, str(valeur))


def niveaux_permis(plancher: str | Sensitivity) -> list[str]:
    """Les niveaux qu'une collection peut prendre au-dessus de ses sources (plancher compris)."""
    return [n.value for n in ECHELLE if rang(n) >= rang(plancher)]


def plafonds_destinations(brut: str) -> dict[str, Sensitivity]:
    """Le réglage des destinations, lu prudemment : une destination inconnue ou un niveau inconnu
    est ignoré (et journalisé), jamais d'erreur au démarrage."""
    brut = (brut or "").strip()
    if not brut:
        return {}
    try:
        donnees = json.loads(brut)
    except ValueError:
        logger.warning("MYCOLLECTIONS_DESTINATIONS_SENSIBILITE_MAX illisible : ignoré")
        return {}
    if not isinstance(donnees, dict):
        logger.warning("MYCOLLECTIONS_DESTINATIONS_SENSIBILITE_MAX n'est pas un objet : ignoré")
        return {}
    rendu: dict[str, Sensitivity] = {}
    for dest, valeur in donnees.items():
        if dest not in DESTINATIONS:
            logger.warning("destination inconnue dans MYCOLLECTIONS_DESTINATIONS_SENSIBILITE_MAX : %s", dest)
            continue
        try:
            rendu[dest] = Sensitivity(valeur)
        except ValueError:
            logger.warning("niveau inconnu pour la destination %s : ignoré", dest)
    return rendu


def plafond(destination: str) -> Sensitivity | None:
    """Le plafond réglé pour cette destination, ou None (aucune restriction)."""
    from app.config import settings

    return plafonds_destinations(settings.destinations_sensibilite_max).get(destination)


def admise(collection_sensibilite: str | None, destination: str) -> bool:
    """La collection peut-elle aller vers cette destination ?"""
    p = plafond(destination)
    return p is None or compatible(niveau(collection_sensibilite), p)


def refus_destination(collection_sensibilite: str | None, destination: str) -> str | None:
    """La phrase qui dit pourquoi la collection ne va pas vers cette destination, ou None."""
    p = plafond(destination)
    if p is None or compatible(niveau(collection_sensibilite), p):
        return None
    return (
        f"{LIBELLES_DESTINATION.get(destination, destination).capitalize()} accepte les collections jusqu'au niveau « {libelle(p)} ». "
        f"Celle-ci est au niveau « {libelle(niveau(collection_sensibilite))} » : elle reste interrogeable dans Mes collections."
    )


def refus_plancher(demande: str | Sensitivity, plancher: str | Sensitivity, origine: str) -> str | None:
    """La phrase qui dit pourquoi ce niveau est trop bas pour les sources de la collection, ou None."""
    if compatible(plancher, demande):
        return None
    return f"Les documents de {origine} sont au niveau « {libelle(plancher)} » : la collection ne peut pas être rangée plus bas."
