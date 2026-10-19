"""Les interfaces du harnais : un planificateur produit un plan, un connecteur cherche dans
une source, un apparieur mesure une ressemblance. Aucune implémentation ici (lot A)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from app.harnais.contrat import Appelant, Contexte, Etape, FicheAssistant, FicheSource, Passage, Plan


class Planificateur(ABC):
    """De la fiche, de la question et du contexte, un plan. Interchangeable : les modules
    `toutes_les_sources`, `regles` et `llm` se comparent sur le banc."""

    nom: ClassVar[str]

    @abstractmethod
    async def plan(self, fiche: FicheAssistant, question: str, contexte: Contexte) -> Plan: ...


class Connecteur(ABC):
    """Une source derrière une interface unique. `amont` : les passages des étapes attendues,
    pour une étape « avec » (au premier incrément, le texte du meilleur passage)."""

    type: ClassVar[str]

    @abstractmethod
    async def chercher(self, etape: Etape, identite: Appelant, *, amont: Sequence[Passage] = ()) -> list[Passage]: ...

    @abstractmethod
    async def fiche(self) -> FicheSource: ...


class Apparieur(ABC):
    """Ressemblance d'un texte à des candidats `(identifiant, texte)`, par score décroissant.
    Sert l'appariement question ↔ « quand » et exemples des consignes, fiches de source,
    questions de référence fiables. Les tests en injectent un déterministe."""

    @abstractmethod
    async def apparier(self, texte: str, candidats: Sequence[tuple[str, str]]) -> list[tuple[str, float]]: ...
