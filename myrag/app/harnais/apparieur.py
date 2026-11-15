"""Les apparieurs : la ressemblance d'une question à des textes (« quand » et exemples des
consignes, fiches de source). Implémentations de `Apparieur` (interfaces.py).

- `ApparieurSacDeMots` : déterministe, sans réseau — celui des tests, et le repli du suivant ;
- `ApparieurEmbeddings` : l'API d'embeddings d'OpenRAG (compatible OpenAI) ; injoignable, mal
  configurée ou en erreur ⇒ repli silencieux sur le sac de mots, jamais une erreur."""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter, OrderedDict
from collections.abc import Sequence

import httpx

from app.harnais.interfaces import Apparieur

logger = logging.getLogger("myrag.harnais")

_MOTS_VIDES = frozenset(
    """le la les un une des du de d l au aux et ou a à en est sont ce ces cet cette il elle ils elles on nous vous je tu
    que qui quoi dont où ne pas plus par pour sur sous dans avec sans se sa son ses leur leurs mon ma mes ton ta tes
    comment quel quelle quels quelles faut faire peut puis y c qu s n m t se si mais donc car ni or""".split()
)  # fmt: skip


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def mots(texte: str) -> list[str]:
    """Les mots qui portent le sens : sans accents ni casse, sans mots vides, au singulier (grossier)."""
    sortie = []
    for m in re.findall(r"[a-z0-9]+", _sans_accents(texte).lower()):
        if m in _MOTS_VIDES or (len(m) < 3 and not m.isdigit()):
            continue
        if len(m) > 4 and m[-1] in "sx":
            m = m[:-1]
        sortie.append(m)
    return sortie


def _cosinus(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    produit = sum(n * b[m] for m, n in a.items() if m in b)
    return produit / (math.sqrt(sum(n * n for n in a.values())) * math.sqrt(sum(n * n for n in b.values())))


class ApparieurSacDeMots(Apparieur):
    """Cosinus de sacs de mots : 1,0 pour deux textes de mêmes mots, 0 sans mot commun."""

    async def apparier(self, texte: str, candidats: Sequence[tuple[str, str]]) -> list[tuple[str, float]]:
        sac = Counter(mots(texte))
        scores = [(ident, round(_cosinus(sac, Counter(mots(t))), 4)) for ident, t in candidats]
        return sorted(scores, key=lambda x: -x[1])  # tri stable : à égalité, l'ordre des candidats


#: Les vecteurs déjà calculés des textes candidats (fiches de collection, « quand » et exemples des consignes),
#: par service, modèle et texte : ils changent peu, la question seule se calcule à chaque appel. Un texte
#: modifié est une autre clé ; les plus anciens sortent au-delà de `MEMOIRE_MAX`. Par processus, jamais la question.
_MEMOIRE: OrderedDict[tuple[str, str, str], list[float]] = OrderedDict()
MEMOIRE_MAX = 5000
#: Textes par appel au service : au-delà, la passerelle refuse (mesuré : 32) et tout retombait sur le sac de mots.
LOT_EMBEDDINGS = 32


def vider_memoire() -> None:
    _MEMOIRE.clear()


class ApparieurEmbeddings(Apparieur):
    """Cosinus des embeddings rendus par `POST {url}/v1/embeddings`."""

    def __init__(self, url: str, modele: str, *, jeton: str = "", delai_s: float = 6.0, repli: Apparieur | None = None):
        self.url, self.modele, self.jeton, self.delai_s = url.rstrip("/"), modele, jeton, delai_s
        self.repli = repli or ApparieurSacDeMots()
        #: Le dernier appel est-il retombé sur le sac de mots ? Ses scores n'ont pas la même échelle.
        self.repli_utilise = False

    async def _vecteurs(self, textes: list[str]) -> list[list[float]]:
        entetes = {"Authorization": f"Bearer {self.jeton}"} if self.jeton else {}
        async with httpx.AsyncClient(timeout=self.delai_s) as client:
            r = await client.post(f"{self.url}/v1/embeddings", json={"model": self.modele, "input": textes}, headers=entetes)
            r.raise_for_status()
            donnees = sorted(r.json()["data"], key=lambda d: d["index"])
        vecteurs = [[float(x) for x in d["embedding"]] for d in donnees]
        if len(vecteurs) != len(textes):
            raise ValueError("nombre de vecteurs inattendu")
        return vecteurs

    async def _vecteurs_en_memoire(self, texte: str, candidats: Sequence[tuple[str, str]]) -> tuple[list[float], list[list[float]]]:
        """Le vecteur de la question (jamais gardé) et ceux des candidats : ceux déjà calculés viennent de la
        mémoire du processus, les autres du service, par lots de `LOT_EMBEDDINGS` textes."""
        cles = [(self.url, self.modele, t) for _, t in candidats]
        manquants = list(dict.fromkeys(t for (_, _, t) in cles if (self.url, self.modele, t) not in _MEMOIRE))
        a_calculer = [texte, *manquants]
        vecteurs: list[list[float]] = []
        for i in range(0, len(a_calculer), LOT_EMBEDDINGS):
            vecteurs.extend(await self._vecteurs(a_calculer[i : i + LOT_EMBEDDINGS]))
        for t, v in zip(manquants, vecteurs[1:], strict=True):
            _MEMOIRE[(self.url, self.modele, t)] = v
            if len(_MEMOIRE) > MEMOIRE_MAX:
                _MEMOIRE.popitem(last=False)
        autres = []
        for cle in cles:
            _MEMOIRE.move_to_end(cle)
            autres.append(_MEMOIRE[cle])
        return vecteurs[0], autres

    async def apparier(self, texte: str, candidats: Sequence[tuple[str, str]]) -> list[tuple[str, float]]:
        if not candidats:
            return []
        try:
            question, autres = await self._vecteurs_en_memoire(texte, candidats)
        except Exception as e:  # injoignable, 4xx/5xx, corps inattendu : on retombe, sans erreur
            logger.info("Embeddings indisponibles (%s) : repli sur le sac de mots", type(e).__name__)
            self.repli_utilise = True
            return await self.repli.apparier(texte, candidats)
        self.repli_utilise = False
        nq = math.sqrt(sum(x * x for x in question)) or 1.0
        scores = []
        for (ident, _), v in zip(candidats, autres, strict=True):
            nv = math.sqrt(sum(x * x for x in v)) or 1.0
            scores.append((ident, round(max(0.0, sum(a * b for a, b in zip(question, v, strict=True)) / (nq * nv)), 4)))
        return sorted(scores, key=lambda x: -x[1])
