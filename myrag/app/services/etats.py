"""La machine à états du collectif — module pur, sans base ni réseau.

Des valeurs entrent, une décision sort ; comme les verdicts du suivi. Tout ce que
l'API refuse ici se teste sans démarrer quoi que ce soit (tests/unit/test_regle*).

Trois règles non négociables vivent ici :
- un chantier ne démarre qu'à N soutiens ET un garant (jamais OU) ;
- une collection avance dans l'ordre amorcee → en_controle → publiee_groupe →
  publiee_tous, sans saut, et « publiée à tous » exige une grille complète — sauf
  forçage par un administrateur, qui laisse une trace ;
- tant qu'elle n'est pas publiée à tous, ses réponses portent la mention.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models.db import ETATS_COLLECTION, utcnow

MENTION_VERIFICATION = "en cours de vérification"
ETATS_DEMANDE_EN_SOMMEIL_POSSIBLE = ("chantier",)


class RefusTransition(Exception):
    """Un passage d'état refusé, avec le code HTTP que la route doit rendre."""

    def __init__(self, motif: str, code: int = 409):
        super().__init__(motif)
        self.motif = motif
        self.code = code


def grille_complete(grille: dict | None) -> bool:
    """Source/licence, données personnelles et fraîcheur renseignées, une relecture au moins."""
    if not grille:
        return False
    textes = (grille.get("source_licence"), grille.get("donnees_perso"), grille.get("fraicheur"))
    if any(not (t or "").strip() for t in textes):
        return False
    return int(grille.get("relecture_n") or 0) >= 1


def transition_collection(
    etat: str | None, cible: str, grille: dict | None, *, forcer: bool = False
) -> str:
    """Rend l'état d'arrivée, ou lève RefusTransition.

    Sans forçage : la cible est l'étape suivante, ou le retour publiee_tous →
    publiee_groupe (un garant peut retirer de la diffusion large) ; publiee_tous exige
    la grille complète. Avec forçage (administrateur) : n'importe quelle cible connue.
    """
    if cible not in ETATS_COLLECTION:
        raise RefusTransition(f"État inconnu : {cible!r}", 422)
    courant = etat if etat in ETATS_COLLECTION else ETATS_COLLECTION[0]
    if cible == courant:
        raise RefusTransition(f"La collection est déjà « {cible} »", 409)
    if forcer:
        return cible
    i, j = ETATS_COLLECTION.index(courant), ETATS_COLLECTION.index(cible)
    retour_autorise = courant == "publiee_tous" and cible == "publiee_groupe"
    if j != i + 1 and not retour_autorise:
        raise RefusTransition(
            f"Passage « {courant} » → « {cible} » refusé : les étapes se franchissent une à une",
            409,
        )
    if cible == "publiee_tous" and not grille_complete(grille):
        raise RefusTransition(
            "Publier à tous exige une grille de contrôle complète : source et licence, "
            "données personnelles, fraîcheur, et au moins une relecture",
            422,
        )
    return cible


def transitions_possibles(etat: str | None, grille: dict | None, *, forcer: bool = False) -> list[str]:
    possibles = []
    for cible in ETATS_COLLECTION:
        try:
            transition_collection(etat, cible, grille, forcer=forcer)
        except RefusTransition:
            continue
        possibles.append(cible)
    return possibles


def demande_atteint_le_chantier(nb_soutiens_distincts: int, a_un_garant: bool, seuil: int) -> bool:
    """ET, jamais OU : le seuil sans garant ne démarre rien, le garant seul non plus."""
    return bool(a_un_garant) and int(nb_soutiens_distincts) >= int(seuil)


def en_sommeil(
    etat: str, dernier_evenement_le: datetime | None, maintenant: datetime | None = None, jours: int = 30
) -> bool:
    """Un chantier sans événement depuis `jours` jours. Jamais pour une demande ouverte."""
    if etat not in ETATS_DEMANDE_EN_SOMMEIL_POSSIBLE:
        return False
    if dernier_evenement_le is None:
        return True
    maintenant = maintenant or utcnow()
    return (maintenant - dernier_evenement_le) > timedelta(days=jours)


def confirmation_echue(
    etat: str, demandee_le: datetime | None, maintenant: datetime | None = None, jours: int = 5
) -> bool:
    """Une demande « à confirmer » dont l'auteur n'a pas répondu depuis `jours` jours."""
    if etat != "a_confirmer" or demandee_le is None:
        return False
    maintenant = maintenant or utcnow()
    return (maintenant - demandee_le) > timedelta(days=jours)


def mention_verification(etat: str | None) -> str | None:
    """La mention que portent les réponses d'une collection non publiée à tous."""
    return None if etat == "publiee_tous" else MENTION_VERIFICATION


def servie_hors_du_groupe(etat: str | None) -> bool:
    """Seule une collection publiée à tous peut être partagée au-delà de son groupe."""
    return etat == "publiee_tous"
