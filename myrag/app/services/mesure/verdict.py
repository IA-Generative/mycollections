"""Les verdicts d'une mesure, en fonctions pures (testées sans réseau).

- une question HORS SUJET attend un refus : `refus_ok` si la réponse refuse explicitement ET
  qu'elle ne vient pas du repli « noms de fichiers » (qui décrit la collection au lieu de
  refuser), `refus_ko` sinon ;
- une réponse sans aucune source documentaire : `sans_source` ;
- sinon le juge tranche (`conforme`, `partiel`, `non_conforme`) ; les mots attendus (`must_cite`)
  plafonnent à `partiel` quand moins de la moitié apparaissent ;
- à défaut de juge, la similarité des textes (grossière, signalée comme telle).
"""

from __future__ import annotations

import unicodedata

PHRASES_REFUS = (
    "pas pu trouver",
    "ne dispose pas",
    "ne dispose d'aucune",
    "aucune information",
    "pas d'information",
    "pas en mesure",
    "ne figure pas",
    "ne figurent pas",
    "ne sais pas",
    "je ne peux pas repondre",
    "ne contiennent pas",
    "ne contient pas",
    "hors du champ",
    "hors sujet",
    "ne traite pas",
    "ne traitent pas",
    "ne permettent pas de repondre",
    "ne mentionnent pas",
    "ne mentionne pas",
    "aucun document",
)

SCORES = {"conforme": 1.0, "refus_ok": 1.0, "partiel": 0.5, "non_conforme": 0.0, "refus_ko": 0.0, "sans_source": 0.0}


def plier(texte: str) -> str:
    t = unicodedata.normalize("NFD", texte or "")
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").lower().replace("’", "'").split())


def est_un_refus(texte: str) -> bool:
    t = plier(texte)
    return any(p in t for p in PHRASES_REFUS)


def verdict_hors_sujet(contenu: str, repli: str) -> tuple[str, str]:
    if repli == "fichiers":
        return "refus_ko", "La collection a décrit ses documents au lieu de refuser la question."
    if est_un_refus(contenu):
        return "refus_ok", "La collection a refusé une question hors de son champ."
    return "refus_ko", "La collection a répondu à une question hors de son champ, au lieu de refuser."


def mots_trouves(contenu: str, must_cite: list[str]) -> list[str]:
    t = plier(contenu)
    return [m for m in must_cite or [] if plier(m) and plier(m) in t]


def plafonner(verdict: str, contenu: str, must_cite: list[str]) -> tuple[str, str | None]:
    """Moins de la moitié des mots attendus présents : au mieux `partiel`."""
    if not must_cite or verdict != "conforme":
        return verdict, None
    trouves = mots_trouves(contenu, must_cite)
    if len(trouves) * 2 < len(must_cite):
        manquants = [m for m in must_cite if m not in trouves]
        return "partiel", f"Mots attendus absents : {', '.join(manquants[:5])}."
    return verdict, None


_VIDES = {
    "le",
    "la",
    "les",
    "un",
    "une",
    "des",
    "de",
    "du",
    "et",
    "est",
    "en",
    "au",
    "aux",
    "a",
    "il",
    "elle",
    "pour",
    "par",
    "sur",
    "que",
    "qui",
    "ne",
    "pas",
    "se",
    "sa",
    "son",
    "ses",
    "dans",
    "avec",
    "ce",
    "cette",
    "l",
    "d",
}


def _mots(texte: str) -> list[str]:
    import re

    return [m for m in re.findall(r"[a-z0-9]+", plier(texte)) if m not in _VIDES and len(m) > 1]


def verdict_similarite(reference: str, obtenue: str) -> tuple[str, float]:
    """Recouvrement des mots porteurs de sens (F1), pas des caractères : deux phrases françaises
    sans rapport partagent beaucoup de lettres, pas de mots."""
    ref, obt = _mots(reference), _mots(obtenue)
    if not ref or not obt:
        return "non_conforme", 0.0
    communs = sum(min(ref.count(m), obt.count(m)) for m in set(ref))
    if not communs:
        return "non_conforme", 0.0
    precision, rappel = communs / len(obt), communs / len(ref)
    f1 = 2 * precision * rappel / (precision + rappel)
    if f1 >= 0.6:
        return "conforme", f1
    if f1 >= 0.3:
        return "partiel", f1
    return "non_conforme", f1


def score_de(verdict: str) -> float | None:
    return SCORES.get(verdict)


def score_global(verdicts: list[str]) -> float | None:
    """Sur 100, les erreurs exclues ; None si rien de mesurable."""
    notes = [SCORES[v] for v in verdicts if v in SCORES]
    return round(100 * sum(notes) / len(notes), 1) if notes else None


def appreciation(score: float | None) -> str:
    if score is None:
        return "non mesurée"
    if score >= 80:
        return "très bonne"
    if score >= 60:
        return "satisfaisante"
    if score >= 40:
        return "à améliorer"
    return "insuffisante"
