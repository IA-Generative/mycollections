"""Les réponses fiables : parmi des réponses de référence que l'équipe a validées et marquées
« fiables », celle dont la question ressemble le plus à la question posée est servie telle quelle,
sans recherche, si la ressemblance atteint le seuil de l'assistant. Module pur : les candidats
sont passés par l'appelant, la ressemblance est celle de l'`Apparieur`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.harnais.contrat import ReponseFiableRetenue
from app.harnais.interfaces import Apparieur


@dataclass(frozen=True)
class Candidat:
    """Une réponse fiable candidat : l'identifiant de `paire_qa`, sa question, sa réponse et sa source (collection)."""

    id: str
    question: str
    reponse: str
    source: str


@dataclass(frozen=True)
class Retenue:
    candidat: Candidat
    score: float

    def reference(self) -> ReponseFiableRetenue:
        return ReponseFiableRetenue(id=self.candidat.id, score=self.score)


async def choisir(question: str, candidates: Sequence[Candidat], apparieur: Apparieur, seuil: float) -> Retenue | None:
    """La candidat la plus proche de `question`, si son score atteint `seuil` ; sinon rien."""
    if not candidates or not question.strip():
        return None
    par_id = {c.id: c for c in candidates}
    classement = await apparieur.apparier(question, [(c.id, c.question) for c in candidates])
    if not classement:
        return None
    ident, score = classement[0]
    if ident not in par_id or score < seuil or score <= 0:
        return None
    return Retenue(par_id[ident], min(1.0, max(0.0, score)))
