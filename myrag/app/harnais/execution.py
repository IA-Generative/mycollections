"""L'exécution d'un plan : les étapes en parallèle, sauf celles qui en attendent d'autres.

Une étape qui `attend` reçoit en amont le meilleur passage de celles qu'elle attend. Une source
qui tombe (5xx, délai, refus) est ignorée et comptée, jamais fatale : les autres répondent. Une
liste de partitions vide n'est jamais envoyée (OpenRAG la lirait comme « toutes »). Module pur :
il ne connaît que les interfaces."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import httpx

from app.harnais.contrat import Appelant, ErreurEtape, Etape, JournalEtape, Passage, Plan
from app.harnais.interfaces import Connecteur

DELAI_DEFAUT_S = 6.0


@dataclass
class SortieEtape:
    etape: Etape
    passages: list[Passage] = field(default_factory=list)
    erreur: ErreurEtape | None = None
    duree_ms: int = 0


@dataclass
class Execution:
    sorties: dict[int, SortieEtape]
    duree_ms: int

    @property
    def par_etape(self) -> dict[int, list[Passage]]:
        return {n: s.passages for n, s in self.sorties.items()}

    @property
    def sources_ignorees(self) -> int:
        """Les sources distinctes tombées en erreur (hors « vide » : une source qui ne trouve rien répond)."""
        return len({s.etape.source for s in self.sorties.values() if s.erreur and s.erreur != "vide"})

    @property
    def toutes_en_panne(self) -> bool:
        return bool(self.sorties) and all(s.erreur in ("panne", "delai") for s in self.sorties.values())

    def journal_etapes(self) -> list[JournalEtape]:
        return [
            JournalEtape(n=n, source=s.etape.source, poids=s.etape.poids, attend=s.etape.attend, duree_ms=s.duree_ms, passages=len(s.passages), erreur=s.erreur)
            for n, s in sorted(self.sorties.items())
        ]


def _classer(e: BaseException) -> ErreurEtape:
    if isinstance(e, (asyncio.TimeoutError, httpx.TimeoutException)):
        return "delai"
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
        return "refus"
    return "panne"


def meilleur(passages: Sequence[Passage]) -> Passage | None:
    """Le meilleur passage : le plus haut score, à défaut le mieux classé."""
    if not passages:
        return None
    return max(passages, key=lambda p: (p.score if p.score is not None else float("-inf"), -p.rang))


def _ms(debut: float) -> int:
    return int((time.monotonic() - debut) * 1000)


async def executer(plan: Plan, connecteurs: Mapping[str, Connecteur], identite: Appelant, *, delai_s: float = DELAI_DEFAUT_S) -> Execution:
    """Exécute `plan`. `connecteurs[source]` sert chaque étape ; une source sans connecteur est
    une étape « refus ». Les étapes indépendantes d'un même connecteur qui sait chercher
    en groupe (`chercher_groupe`, une requête multi-partitions) partent ensemble."""
    debut = time.monotonic()
    etapes = {e.n: e for e in plan.etapes}
    taches: dict[int, asyncio.Task[SortieEtape]] = {}
    groupes = _groupes(plan, connecteurs)
    groupe_de: dict[int, asyncio.Task[dict[int, SortieEtape]]] = {}
    for membres, conn in groupes:
        t = asyncio.ensure_future(_chercher_groupe(conn, membres, identite, delai_s))
        for e in membres:
            groupe_de[e.n] = t

    async def une(e: Etape) -> SortieEtape:
        if e.n in groupe_de:
            return (await groupe_de[e.n])[e.n]
        amont: list[Passage] = []
        if e.attend:
            attendues = await asyncio.gather(*(taches[a] for a in e.attend))
            amont = [p for p in (meilleur(s.passages) for s in attendues) if p is not None]
        return await _chercher(connecteurs.get(e.source), e, identite, amont, delai_s)

    for n in sorted(etapes):
        taches[n] = asyncio.ensure_future(une(etapes[n]))
    sorties = dict(zip(taches, await asyncio.gather(*taches.values())))
    return Execution(sorties=sorties, duree_ms=_ms(debut))


def _groupes(plan: Plan, connecteurs: Mapping[str, Connecteur]) -> list[tuple[list[Etape], Connecteur]]:
    """Les étapes indépendantes de même question et de même connecteur « groupable »."""
    paquets: dict[tuple[int, str], list[Etape]] = {}
    for e in plan.etapes:
        conn = connecteurs.get(e.source)
        if e.attend or conn is None or not hasattr(conn, "chercher_groupe"):
            continue
        paquets.setdefault((id(conn), e.question), []).append(e)
    return [(m, connecteurs[m[0].source]) for m in paquets.values() if len(m) > 1]


async def _chercher(conn: Connecteur | None, e: Etape, identite: Appelant, amont: Sequence[Passage], delai_s: float) -> SortieEtape:
    debut = time.monotonic()
    if conn is None:
        return SortieEtape(e, [], "refus", _ms(debut))
    try:
        passages = await asyncio.wait_for(conn.chercher(e, identite, amont=amont), timeout=delai_s)
    except Exception as exc:  # une source qui tombe ne fait pas tomber les autres
        return SortieEtape(e, [], _classer(exc), _ms(debut))
    passages = [p for p in passages if p.source == e.source]
    return SortieEtape(e, passages, None if passages else "vide", _ms(debut))


async def _chercher_groupe(conn, membres: list[Etape], identite: Appelant, delai_s: float) -> dict[int, SortieEtape]:
    debut = time.monotonic()
    try:
        rendu: dict[int, list[Passage]] = await asyncio.wait_for(conn.chercher_groupe(membres, identite), timeout=delai_s)
    except Exception:
        # Une partition refusée ou en panne gâte l'appel groupé : chaque étape reprend seule.
        sorties = await asyncio.gather(*(_chercher(conn, e, identite, (), delai_s) for e in membres))
        return {s.etape.n: s for s in sorties}
    duree = _ms(debut)
    sortie = {}
    for e in membres:
        passages = [p for p in rendu.get(e.n, []) if p.source == e.source]
        sortie[e.n] = SortieEtape(e, passages, None if passages else "vide", duree)
    return sortie
