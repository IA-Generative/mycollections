"""Le planificateur par règles : la question est rapprochée du « quand » et des exemples des
consignes ; une consigne reconnue fixe les étapes, sinon les régimes des sources décident.

- consigne reconnue (ressemblance ≥ `seuil`) ⇒ ses étapes dans l'ordre, chaînées par `avec`
  (une étape « avec » attend la précédente) ; les sources `toujours` que ses étapes ne citent
  pas s'y ajoutent, à poids réduit ;
- sinon ⇒ les sources `toujours`, plus les `selon_question` dont la fiche ressemble à la question
  (≥ `seuil_source`) ; JAMAIS les `sur_consigne`, qui n'existent que citées par une consigne ;
- une consigne « toujours » qui a des étapes sert de consigne par défaut quand rien d'autre ne
  correspond ;
- si rien n'est retenu, toutes les `selon_question` lisibles : un assistant ne reste jamais muet.

Une source hors `Contexte.sources_lisibles` n'est jamais planifiée ; elle est comptée."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from app.harnais.contrat import QUAND_TOUJOURS, Consigne, Contexte, Etape, FicheAssistant, Plan
from app.harnais.interfaces import Apparieur, Planificateur

SEUIL_CONSIGNE = 0.3
SEUIL_SOURCE = 0.15
#: Poids d'une source `toujours` ajoutée à une consigne qui ne la cite pas.
POIDS_TOUJOURS_AJOUTEE = 0.5


class Regles(Planificateur):
    nom: ClassVar[str] = "regles"

    def __init__(
        self,
        apparieur: Apparieur,
        *,
        version: int = 1,
        descriptions: Mapping[str, str] | None = None,
        seuil: float = SEUIL_CONSIGNE,
        seuil_source: float = SEUIL_SOURCE,
    ):
        self.apparieur, self.version = apparieur, version
        #: source → texte qui la décrit (titre et description de la collection) : de quoi juger si elle ressemble à la question.
        self.descriptions = descriptions or {}
        self.seuil, self.seuil_source = seuil, seuil_source

    async def plan(self, fiche: FicheAssistant, question: str, contexte: Contexte) -> Plan:
        lisibles = set(contexte.sources_lisibles)
        consigne, score = await self._reconnaitre(fiche, question)
        if consigne is not None and consigne.chercher:
            etapes = self._etapes_de_consigne(fiche, consigne, question, lisibles)
        else:
            etapes = await self._etapes_par_regimes(fiche, question, lisibles)  # reconnue sans étape : elle ne sert qu'à rédiger
        return Plan(
            assistant=fiche.assistant,
            version=self.version,
            planificateur="regles",
            consigne=consigne.id if consigne else None,
            score_consigne=score if consigne else None,
            etapes=etapes,
            sources_ignorees=len(self._visees(fiche, consigne) - lisibles),
            a_valider=fiche.validation_requise and "valider" in contexte.capacites_client,
        )

    @staticmethod
    def _visees(fiche: FicheAssistant, consigne: Consigne | None) -> set[str]:
        """Les sources que le plan voulait atteindre : celles de la consigne et les `toujours`, sinon toutes sauf `sur_consigne`."""
        if consigne is not None and consigne.chercher:
            return {e.source for e in consigne.chercher} | {s.id for s in fiche.sources if s.regime == "toujours"}
        return {s.id for s in fiche.sources if s.regime != "sur_consigne"}

    async def _reconnaitre(self, fiche: FicheAssistant, question: str) -> tuple[Consigne | None, float]:
        """La consigne dont le « quand » ou un exemple ressemble le plus à la question, au-dessus du seuil."""
        candidats: list[tuple[str, str]] = []
        for i, c in enumerate(fiche.consignes):
            if c.quand == QUAND_TOUJOURS:
                continue
            for j, texte in enumerate([c.quand, *c.exemples]):
                candidats.append((f"{i}:{j}", texte))
        if candidats:
            classes = await self.apparieur.apparier(question, candidats)
            if classes and classes[0][1] >= self.seuil:
                return fiche.consignes[int(classes[0][0].split(":")[0])], round(min(1.0, classes[0][1]), 4)
        par_defaut = next((c for c in fiche.consignes if c.quand == QUAND_TOUJOURS and c.chercher), None)
        return par_defaut, 0.0

    def _etapes_de_consigne(self, fiche: FicheAssistant, consigne: Consigne, question: str, lisibles: set[str]) -> list[Etape]:
        etapes: list[Etape] = []
        numero_precedent: int | None = None  # None : l'étape précédente a disparu (source illisible)
        for e in consigne.chercher:
            if e.source not in lisibles:
                numero_precedent = None
                continue
            n = len(etapes) + 1
            attend = [numero_precedent] if e.avec and numero_precedent else []
            etapes.append(Etape(n=n, source=e.source, question=question, poids=1.0, attend=attend, avec=e.avec if attend else None))
            numero_precedent = n
        deja = {e.source for e in etapes}
        for s in fiche.sources_ordonnees():
            if s.regime == "toujours" and s.id in lisibles and s.id not in deja:
                etapes.append(Etape(n=len(etapes) + 1, source=s.id, question=question, poids=POIDS_TOUJOURS_AJOUTEE))
        return etapes

    async def _etapes_par_regimes(self, fiche: FicheAssistant, question: str, lisibles: set[str]) -> list[Etape]:
        sources = [s for s in fiche.sources_ordonnees() if s.id in lisibles]
        retenues: list[tuple[str, float]] = [(s.id, 1.0) for s in sources if s.regime == "toujours"]
        selon = [s for s in sources if s.regime == "selon_question"]
        decrites = [(s.id, self.descriptions[s.id]) for s in selon if self.descriptions.get(s.id, "").strip()]
        if decrites:
            scores = dict(await self.apparieur.apparier(question, decrites))
            retenues += [(s.id, round(min(1.0, max(0.5, scores[s.id])), 2)) for s in selon if scores.get(s.id, 0.0) >= self.seuil_source]
        if not retenues:
            retenues = [(s.id, 0.5) for s in selon]
        return [Etape(n=i, source=src, question=question, poids=p) for i, (src, p) in enumerate(retenues, start=1)]
