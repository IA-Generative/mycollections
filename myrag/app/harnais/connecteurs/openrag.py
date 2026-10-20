"""Le connecteur des collections : `OpenRAGClient.search`, une requête par étape, ou UNE requête
multi-partitions pour des étapes indépendantes qui posent la même question.

Le connecteur ne juge pas des droits (c'est le périmètre) et ne signe aucun lien : il rend des
passages bruts, `source` = la partition d'où vient le morceau."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import ClassVar

from app.config import settings
from app.harnais.contrat import IDENT_MORCEAU, Appelant, Etape, FicheSource, Passage
from app.harnais.interfaces import Connecteur
from app.services.morceau import decouper_morceau
from app.services.nommage import titre_affiche
from app.services.openrag_client import DocumentRecherche, OpenRAGClient

_CLES_SCORE = ("relevance_score", "rerank_score", "combined_score", "score")
_CLES_DATE = ("created_at", "modified_at", "date", "indexed_at")
_ID_LIEN = re.compile(r"/extract/([^/?#\s]+)")


def _score(meta: dict) -> float | None:
    for cle in _CLES_SCORE:
        v = meta.get(cle)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return round(float(v), 4)
    return None


def _date(meta: dict) -> datetime | None:
    for cle in _CLES_DATE:
        v = meta.get(cle)
        try:
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                return datetime.fromtimestamp(v, tz=timezone.utc)
            if isinstance(v, str) and v.strip():
                dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, OverflowError, OSError):
            continue
    return None


def _ident(doc: DocumentRecherche, meta: dict) -> str | None:
    ident = meta.get("_id")
    if ident is None:
        m = _ID_LIEN.search(str(doc.link or ""))
        ident = m.group(1) if m else None
    ident = str(ident) if ident is not None else ""
    return ident if re.fullmatch(IDENT_MORCEAU, ident) else None


def vers_passage(doc: DocumentRecherche, *, etape: int, rang: int) -> Passage | None:
    """Un document de `/search` en passage ; None s'il n'a ni partition ni texte."""
    meta = doc.metadata if isinstance(doc.metadata, dict) else {}
    partition = meta.get("partition")
    if not isinstance(partition, str) or not partition:
        return None
    _, fichier, corps = decouper_morceau(doc.content)
    if not corps.strip():
        return None
    ident = _ident(doc, meta)
    titre = meta.get("title") if isinstance(meta.get("title"), str) else ""
    fichier_nom = (meta.get("filename") if isinstance(meta.get("filename"), str) else "") or fichier or ""
    nom = titre.strip() or titre_affiche(fichier_nom)
    page = meta.get("page")
    return Passage(
        source=partition,
        etape=etape,
        rang=rang,
        score=_score(meta),
        ident=ident,
        document=str(meta.get("file_id") or ident or fichier or partition),
        titre=re.sub(r"\.(md|txt|markdown)$", "", nom.strip(), flags=re.I)[:200],
        date=_date(meta),
        page=page if isinstance(page, int) and not isinstance(page, bool) and page > 0 else None,
        texte=corps,
    )


class ConnecteurOpenRAG(Connecteur):
    type: ClassVar[str] = "collection"

    def __init__(self, *, top_k: int = 20, delai_s: float | None = None):
        self.top_k = top_k
        self.delai_s = settings.recherche_delai_s if delai_s is None else delai_s

    async def _rechercher(self, partitions: list[str], question: str) -> list[DocumentRecherche]:
        if not partitions:  # jamais une liste vide : OpenRAG la lirait comme « toutes »
            return []
        rendu = await OpenRAGClient(timeout=self.delai_s).search(partitions, question, top_k=self.top_k)
        return rendu.documents

    @staticmethod
    def _passages(docs: Sequence[DocumentRecherche], etape: int) -> list[Passage]:
        passages: list[Passage] = []
        for d in docs:
            p = vers_passage(d, etape=etape, rang=len(passages) + 1)
            if p is not None:
                passages.append(p)
        return passages

    async def chercher(self, etape: Etape, identite: Appelant, *, amont: Sequence[Passage] = ()) -> list[Passage]:
        question = etape.question
        if etape.avec and amont:
            # Le relais : le texte du meilleur passage trouvé en amont précise la question.
            question = f"{question}\n{amont[0].texte[:500]}"[:1000]
        docs = await self._rechercher([etape.source], question)
        return self._passages(docs, etape.n)

    async def chercher_groupe(self, etapes: Sequence[Etape], identite: Appelant) -> dict[int, list[Passage]]:
        """Une seule requête pour plusieurs étapes indépendantes de même question ; chaque
        morceau retourne à l'étape de sa partition, dans l'ordre d'arrivée."""
        if not etapes:
            return {}
        par_partition = {e.source: e for e in etapes}
        docs = await self._rechercher(list(par_partition), etapes[0].question)
        rendu: dict[int, list[Passage]] = {e.n: [] for e in etapes}
        for d in docs:
            meta = d.metadata if isinstance(d.metadata, dict) else {}
            e = par_partition.get(meta.get("partition"))
            if e is None:
                continue
            p = vers_passage(d, etape=e.n, rang=len(rendu[e.n]) + 1)
            if p is not None:
                rendu[e.n].append(p)
        return rendu

    async def fiche(self) -> FicheSource:
        return FicheSource(id="collections", type="collection", titre="Collections")
