"""Le planificateur le plus simple : toutes les sources lisibles, à poids égaux, en parallèle.

Sert de repli et de ligne de base du banc. Il ne lit ni les consignes ni le régime des sources :
le périmètre (`Contexte.sources_lisibles`) est déjà calculé, il ne le recalcule pas."""

from __future__ import annotations

from typing import ClassVar

from app.harnais.contrat import Contexte, Etape, FicheAssistant, Plan
from app.harnais.interfaces import Planificateur


class ToutesLesSources(Planificateur):
    nom: ClassVar[str] = "toutes_les_sources"

    def __init__(self, version: int = 1):
        self.version = version

    async def plan(self, fiche: FicheAssistant, question: str, contexte: Contexte) -> Plan:
        lisibles = set(contexte.sources_lisibles)
        etapes = [Etape(n=n, source=s.id, question=question, poids=1.0) for n, s in enumerate((s for s in fiche.sources_ordonnees() if s.id in lisibles), start=1)]
        return Plan(
            assistant=fiche.assistant,
            version=self.version,
            planificateur="toutes_les_sources",
            etapes=etapes,
            sources_ignorees=len(fiche.sources) - len(etapes),
            a_valider=fiche.validation_requise and "valider" in contexte.capacites_client,
        )
