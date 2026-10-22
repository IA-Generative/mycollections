"""Le connecteur du référentiel d'éligibilité : un service HTTP interne, sans authentification, qui
sert des tableaux (titres de séjour → situations → pièces justificatives).

La recherche du service est un `ILIKE '%texte%'` sur toutes les colonnes : la question entière n'y
correspond presque jamais. On en tire donc quelques mots significatifs, un appel par mot (trois au
plus par table), et on classe les lignes par nombre de mots retrouvés. Une étape « avec » cherche
la référence courte (numéro d'article, intitulé) du meilleur passage amont.

Le service ne connaît ni personne ni droit : aucun en-tête, aucun identifiant n'est envoyé, et
`/query` n'est pas utilisé (pas de SQL construit à partir d'une question). Une panne, un délai ou
une réponse illisible rendent une liste vide, jamais une exception."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from typing import Any, ClassVar

import httpx

from app.harnais.contrat import Appelant, Etape, FicheSource, Passage
from app.harnais.interfaces import Connecteur

logger = logging.getLogger(__name__)

APPELS_PAR_TABLE = 3
LIGNES_PAR_APPEL = 20
PASSAGES_MAX = 10
MOT_MIN = 3
REFERENCE_MAX = 80

MOTS_VIDES = frozenset(
    """
    alors apres assez aucun aussi autre avec avez avoir bien cela celle celui ces cette chez comme comment dans
    des doit donc dont elle elles encore entre est etre faire fait faut leur leurs mais meme mes moi mon nos notre
    nous obtenir ont par parce pas peut peux plus pour pourquoi pouvez quand que quel quelle quelles quels qui quoi
    sans ses sont sous sur tes toi ton tous tout toute toutes tres une uns vos votre vous les aux
    """.split()
)
_MOT = re.compile(r"[a-z0-9]+")
_ARTICLE = re.compile(r"\b(?:article\s+)?[LRD]\.?\s?\d+(?:[-.]\d+)*\b", re.IGNORECASE)


def _normaliser(texte: str) -> str:
    """En minuscules, sans accents."""
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def mots_significatifs(question: str) -> list[tuple[str, str]]:
    """Les mots utiles de la question, du plus spécifique (le plus long) au moins : `(forme à chercher, forme normalisée)`.
    La forme à chercher garde les accents (c'est elle que le service compare) ; sans doublon."""
    vus: set[str] = set()
    mots: list[tuple[str, str]] = []
    for brut in re.findall(r"\w+", question.lower()):
        norme = _normaliser(brut)
        if not _MOT.fullmatch(norme) or norme in vus or norme in MOTS_VIDES:
            continue
        if len(norme) < MOT_MIN and not any(c.isdigit() for c in norme):
            continue
        vus.add(norme)
        mots.append((brut, norme))
    return sorted(mots, key=lambda m: -len(m[1]))  # le tri est stable : à longueur égale, l'ordre de la question


def reference_courte(passage: Passage) -> str:
    """La référence à chercher à partir d'un passage amont : un numéro d'article, sinon son titre."""
    m = _ARTICLE.search(f"{passage.titre}\n{passage.texte[:1000]}")
    if m:
        return re.sub(r"^article\s+", "", m.group(0), flags=re.IGNORECASE).strip()
    titre = passage.titre.strip()
    if titre:
        return titre[:REFERENCE_MAX].strip()
    return (passage.texte.strip().splitlines() or [""])[0][:REFERENCE_MAX].strip()


def _valeur(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return str(v).strip()


def empreinte_ligne(table: str, ligne: dict) -> str:
    """Stable d'un appel à l'autre : l'ordre des colonnes ne compte pas."""
    contenu = json.dumps({"t": table, "l": ligne}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()[:16]


#: Au-delà, une valeur est un contenu (la liste des pièces…), pas un intitulé.
LONGUEUR_INTITULE = 120


def _intitules(ligne: dict) -> list[tuple[str, str]]:
    """Les valeurs qui peuvent nommer la ligne, dans l'ordre : ni vides, ni identifiants, ni nombres."""
    rendu = []
    for nom, v in ligne.items():
        texte = " ".join(_valeur(v).split())
        if not texte or nom.lower() == "id" or nom.lower().endswith("_id") or texte.replace(".", "").isdigit():
            continue
        rendu.append((nom, texte))
    return rendu


def titre_de_ligne(ligne: dict) -> str:
    """Le titre d'une ligne : les deux intitulés qui précèdent son premier contenu long (par exemple le
    titre de séjour et la situation, avant la liste des pièces), car les premières colonnes d'un
    référentiel sont souvent des regroupements communs à toutes les lignes ; sans contenu long, le
    premier intitulé."""
    valeurs = _intitules(ligne)
    longs = [i for i, (_, v) in enumerate(valeurs) if len(v) > LONGUEUR_INTITULE]
    if longs:
        courts = [v for _, v in valeurs[: longs[0]] if len(v) <= LONGUEUR_INTITULE]
        if courts:
            return " — ".join(v.rstrip(" :") for v in courts[-2:])
    courts = [v for _, v in valeurs if len(v) <= LONGUEUR_INTITULE]
    return courts[0].rstrip(" :") if courts else ""


def libelle_colonne(nom: str) -> str:
    """« titre_pour_eligibilite » → « Titre pour eligibilite » : un nom de colonne qui se lit."""
    mots = " ".join(str(nom).replace("_", " ").split())
    return mots[:1].upper() + mots[1:]


class ConnecteurEligibilite(Connecteur):
    type: ClassVar[str] = "connecteur"

    def __init__(
        self,
        *,
        ident: str,
        url: str,
        titre: str,
        tables: Sequence[str],
        description: str = "",
        exemples: Sequence[str] = (),
        delai_s: float = 6.0,
        client: httpx.AsyncClient | None = None,
        passages_max: int = PASSAGES_MAX,
    ):
        self.ident, self.url, self.titre = ident, url.rstrip("/"), titre
        self.tables, self.description, self.exemples = list(tables), description, list(exemples)
        self.delai_s, self.client, self.passages_max = delai_s, client, passages_max

    async def fiche(self) -> FicheSource:
        return FicheSource(id=self.ident, type="connecteur", titre=self.titre, description=self.description, exemples=self.exemples, relais=["reference"])

    async def _lignes(self, client: httpx.AsyncClient, table: str, q: str) -> list[dict]:
        """Les lignes que le service rend pour `q` ; rien si la table est inconnue ou si l'appel échoue."""
        try:
            r = await client.get(f"{self.url}/tables/{table}/search", params={"q": q, "limit": LIGNES_PAR_APPEL})
            r.raise_for_status()
            corps = r.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("Connecteur %s : la table %s n'a pas répondu", self.ident, table)
            return []
        return [ligne for ligne in corps if isinstance(ligne, dict)] if isinstance(corps, list) else []

    async def _recherches(self, termes: list[str]) -> list[tuple[str, dict]]:
        async def tout(client: httpx.AsyncClient):
            taches = [self._lignes(client, t, q) for t in self.tables for q in termes]
            noms = [t for t in self.tables for _ in termes]
            return list(zip(noms, await asyncio.gather(*taches)))

        if self.client is not None:
            lots = await tout(self.client)
        else:
            async with httpx.AsyncClient(timeout=self.delai_s) as client:
                lots = await tout(client)
        return [(table, ligne) for table, lignes in lots for ligne in lignes]

    async def chercher(self, etape: Etape, identite: Appelant, *, amont: Sequence[Passage] = ()) -> list[Passage]:
        # `identite` n'est volontairement pas lue : le service ne connaît personne.
        if etape.avec and amont:
            reference = reference_courte(amont[0])
            termes = [reference] if reference else []
            mots = [(reference, _normaliser(reference))] if reference else []
        else:
            mots = mots_significatifs(etape.question)
            termes = [forme for forme, _ in mots[:APPELS_PAR_TABLE]]
        if not termes:
            return []
        try:
            trouvees = await asyncio.wait_for(self._recherches(termes), timeout=self.delai_s)
        except (asyncio.TimeoutError, httpx.HTTPError):
            return []
        return self._classer(trouvees, etape.n, mots)

    def _classer(self, trouvees: list[tuple[str, dict]], n: int, mots: list[tuple[str, str]]) -> list[Passage]:
        normes = [m for _, m in mots]
        candidates: dict[str, tuple[int, str, dict]] = {}
        for table, ligne in trouvees:
            cle = f"{table}:{empreinte_ligne(table, ligne)}"
            if cle in candidates:
                continue
            fond = _normaliser(" ".join(_valeur(v) for v in ligne.values()))
            candidates[cle] = (sum(1 for m in normes if m in fond), table, ligne)
        classees = sorted(candidates.items(), key=lambda kv: -kv[1][0])  # stable : à égalité, l'ordre du service
        passages: list[Passage] = []
        for cle, (retrouves, table, ligne) in classees:
            texte = "\n".join(f"{libelle_colonne(nom)} : {v}" for nom, val in ligne.items() if (v := _valeur(val)))
            if not texte:
                continue
            titre = titre_de_ligne(ligne) or self.titre
            passages.append(
                Passage(
                    source=self.ident,
                    etape=n,
                    rang=len(passages) + 1,
                    score=round(retrouves / len(normes), 4) if normes else None,
                    document=cle,
                    titre=titre[:200],
                    texte=texte,
                    meta={"table": table},
                )
            )
            if len(passages) >= self.passages_max:
                break
        return passages
