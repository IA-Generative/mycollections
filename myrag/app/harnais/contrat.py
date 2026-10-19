"""Le contrat : la fiche d'un assistant, le plan de recherche, les passages, le résultat et ce
qui s'en journalise. Des modèles Pydantic, des constantes, deux fonctions pures.

La fiche est une DONNÉE, pas un prompt. Une publication en fige une version : le texte
canonique (`canonique`) et son empreinte sha256 (`empreinte`). Le journal d'un plan ne porte
jamais la question ni un contenu : `JournalPlan` n'a aucun champ de texte libre.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

CONTRAT_VERSION = 1
#: Identifiant stable d'un assistant, d'une source ou d'une consigne.
IDENT_ASSISTANT = r"^[a-z0-9][a-z0-9._-]{2,63}$"
#: Nom d'un relais entre deux étapes (« avec: article_trouve »).
IDENT_RELAIS = r"^[a-z][a-z0-9_]{1,40}$"
IDENT_MORCEAU = r"^[A-Za-z0-9_-]{1,128}$"
TYPES_SOURCE = ("collection", "connecteur")
REGIMES_SOURCE = ("toujours", "selon_question", "sur_consigne")
#: Valeur réservée de `Consigne.quand` : la consigne s'applique à toute question.
QUAND_TOUJOURS = "toujours"
CANAUX = ("socle", "portail", "fenetre_js", "api")
CANAUX_JOURNAL = (*CANAUX, "bac-a-sable", "banc")
PLANIFICATEURS = ("toutes_les_sources", "regles", "llm")
CAPACITES_CLIENT = ("valider", "questionner", "panneau")
ERREURS_ETAPE = ("delai", "refus", "panne", "vide")

TypeSource = Literal["collection", "connecteur"]
Regime = Literal["toujours", "selon_question", "sur_consigne"]
Canal = Literal["socle", "portail", "fenetre_js", "api", "bac-a-sable", "banc"]
NomPlanificateur = Literal["toutes_les_sources", "regles", "llm"]
CapaciteClient = Literal["valider", "questionner", "panneau"]
ErreurEtape = Literal["delai", "refus", "panne", "vide"]


class _Modele(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ─── La fiche ────────────────────────────────────────────────────────────────────────────────


class Source(_Modele):
    """Une collection (partition OpenRAG) ou un connecteur du catalogue, et son régime :
    `toujours` interrogée, `selon_question` si sa fiche ressemble à la question, `sur_consigne`
    seulement quand une consigne la cite."""

    id: str = Field(pattern=IDENT_ASSISTANT)
    type: TypeSource
    regime: Regime = "selon_question"
    rang: int | None = Field(default=None, ge=1)


class EtapeConsigne(_Modele):
    source: str = Field(pattern=IDENT_ASSISTANT)
    #: Relais : l'étape reçoit ce que l'étape précédente a trouvé (« article_trouve »).
    avec: str | None = Field(default=None, pattern=IDENT_RELAIS)


class Consigne(_Modele):
    """Quand (une phrase, des exemples) / chercher (des sources, dans l'ordre) / répondre."""

    id: str = Field(pattern=IDENT_ASSISTANT)
    quand: str = Field(min_length=1, max_length=500)
    exemples: list[str] = Field(default_factory=list, max_length=10)
    chercher: list[EtapeConsigne] = Field(default_factory=list)
    repondre: str = Field(default="", max_length=4000)
    #: Clé d'un gabarit de prompt existant (`prompt_template`) ; `repondre` le complète.
    gabarit: str | None = Field(default=None, max_length=100)

    @field_validator("exemples")
    @classmethod
    def _exemples_bornes(cls, v: list[str]) -> list[str]:
        propres = [e.strip() for e in v]
        if any(not e or len(e) > 500 for e in propres):
            raise ValueError("un exemple fait entre 1 et 500 caractères")
        return propres

    @model_validator(mode="after")
    def _avec_pas_en_premier(self):
        if self.chercher and self.chercher[0].avec:
            raise ValueError("« avec » n'a pas de sens sur la première étape : rien n'a encore été trouvé")
        return self


class Canaux(_Modele):
    """Où l'assistant est servi. Hors de l'empreinte : cocher un canal ne fait pas une version."""

    socle: bool = False
    portail: bool = False
    fenetre_js: bool = False
    api: bool = False


class ReferenceResume(_Modele):
    """Dérivé, jamais saisi : l'union des jeux de questions des sources et les questions propres."""

    questions: int = 0
    fiables: int = 0
    par_source: dict[str, int] = Field(default_factory=dict)


class FicheAssistant(_Modele):
    contrat: Literal[1] = CONTRAT_VERSION
    assistant: str = Field(pattern=IDENT_ASSISTANT)
    titre: str = Field(min_length=1, max_length=255)
    rubrique: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=2000)
    sources: list[Source] = Field(min_length=1, max_length=20)
    consignes: list[Consigne] = Field(default_factory=list, max_length=50)
    #: Au-dessus de ce score, une question de référence « fiable » est servie sans recherche.
    seuil_fiable: float = Field(default=0.9, ge=0, le=1)
    validation_requise: bool = False
    publication: Canaux = Field(default_factory=Canaux)
    reference: ReferenceResume | None = None

    @model_validator(mode="after")
    def _coherence(self):
        ids = [s.id for s in self.sources]
        if len(set(ids)) != len(ids):
            raise ValueError("deux sources portent le même identifiant")
        cles = [c.id for c in self.consignes]
        if len(set(cles)) != len(cles):
            raise ValueError("deux consignes portent le même identifiant")
        if sum(1 for c in self.consignes if c.quand == QUAND_TOUJOURS) > 1:
            raise ValueError("une seule consigne peut valoir « toujours »")
        for c in self.consignes:
            for e in c.chercher:
                if e.source not in ids:
                    raise ValueError(f"la consigne « {c.id} » cherche dans « {e.source} », qui n'est pas une source de l'assistant")
        return self

    def sources_ordonnees(self) -> list[Source]:
        """Par rang croissant, les sources sans rang en dernier, dans l'ordre de saisie."""
        return sorted(self.sources, key=lambda s: (s.rang is None, s.rang or 0))

    @classmethod
    def depuis_canonique(cls, contenu_json: str, publication: Canaux | None = None) -> FicheAssistant:
        """La fiche d'une version publiée, avec les canaux du moment (hors de la version)."""
        d = json.loads(contenu_json)
        if publication is not None:
            d["publication"] = publication.model_dump()
        return cls.model_validate(d)


class FicheSource(_Modele):
    """Ce qu'un connecteur dit de lui-même : sert l'index du planificateur et l'onglet Sources."""

    id: str = Field(pattern=IDENT_ASSISTANT)
    type: TypeSource
    titre: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    exemples: list[str] = Field(default_factory=list, max_length=10)
    #: Les relais que le connecteur sait recevoir (valeurs possibles de `avec`).
    relais: list[str] = Field(default_factory=list)


# ─── Le plan ─────────────────────────────────────────────────────────────────────────────────


class Contexte(_Modele):
    """Ce que le service sait au moment de planifier. `sources_lisibles` est le périmètre DÉJÀ
    calculé (fiche ∩ droits de la personne) : un planificateur ne le recalcule jamais."""

    canal: Canal
    capacites_client: set[CapaciteClient] = Field(default_factory=set)
    sources_lisibles: list[str] = Field(default_factory=list)
    top_k: int = Field(default=20, ge=1, le=200)


class Appelant(_Modele):
    """La personne pour qui on cherche. Le jeton ne se lit qu'explicitement (`get_secret_value`)."""

    sub: str = Field(min_length=1)
    groupes: list[str] = Field(default_factory=list)
    jeton: SecretStr | None = None


class Etape(_Modele):
    n: int = Field(ge=1)
    source: str
    #: La question, ou une sous-question. Jamais journalisée.
    question: str = Field(min_length=1, max_length=1000)
    poids: float = Field(default=1.0, gt=0, le=1)
    attend: list[int] = Field(default_factory=list)
    avec: str | None = Field(default=None, pattern=IDENT_RELAIS)

    @model_validator(mode="after")
    def _avec_exige_attend(self):
        if self.avec and not self.attend:
            raise ValueError("une étape « avec » attend au moins une étape")
        return self


class ReponseFiableRetenue(_Modele):
    #: `paire_qa.id` de la question de référence servie.
    id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class Plan(_Modele):
    """La sortie du planificateur, l'entrée de l'exécution. Montrable à la personne."""

    assistant: str = Field(pattern=IDENT_ASSISTANT)
    version: int = Field(ge=1)
    planificateur: NomPlanificateur
    consigne: str | None = None
    score_consigne: float | None = Field(default=None, ge=0, le=1)
    reponse_fiable: ReponseFiableRetenue | None = None
    etapes: list[Etape] = Field(default_factory=list)
    #: Un compte, jamais des noms : ne pas divulguer l'existence d'une source hors droit.
    sources_ignorees: int = Field(default=0, ge=0)
    a_valider: bool = False

    @model_validator(mode="after")
    def _etapes_en_ordre(self):
        numeros = [e.n for e in self.etapes]
        if len(set(numeros)) != len(numeros):
            raise ValueError("deux étapes portent le même numéro")
        for e in self.etapes:
            for a in e.attend:
                if a >= e.n or a not in numeros:
                    raise ValueError(f"l'étape {e.n} attend l'étape {a}, qui ne la précède pas")
        if self.reponse_fiable is not None and self.etapes:
            raise ValueError("une réponse fiable retenue dispense de toute étape")
        return self


# ─── Les passages et le résultat ─────────────────────────────────────────────────────────────


class Passage(_Modele):
    """Un morceau rendu par une source. `document` est la clé du document dans la source
    (file_id OpenRAG, identifiant d'une table…) ; `ident` celle du morceau."""

    source: str
    etape: int = Field(ge=1)
    rang: int = Field(ge=1)
    score: float | None = None
    ident: str | None = Field(default=None, pattern=IDENT_MORCEAU)
    document: str = Field(min_length=1)
    titre: str = ""
    date: datetime | None = None
    page: int | None = Field(default=None, ge=1)
    texte: str
    url: str | None = None
    meta: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Resultat(_Modele):
    plan: Plan
    passages: list[Passage] = Field(default_factory=list)
    #: Rempli seulement par la voie « passages + modèle » (règles « répondre »).
    reponse: str | None = None
    duree_ms: int = Field(ge=0)
    par_source: dict[str, int] = Field(default_factory=dict)


# ─── Le journal ──────────────────────────────────────────────────────────────────────────────


class JournalEtape(_Modele):
    n: int = Field(ge=1)
    source: str
    poids: float
    attend: list[int] = Field(default_factory=list)
    duree_ms: int = Field(ge=0)
    passages: int = Field(ge=0)
    erreur: ErreurEtape | None = None


class JournalPlan(_Modele):
    """Ce qui s'écrit d'un plan : identifiants, sources, poids, durées, consigne retenue, réponse
    fiable ou non. Aucun champ de texte libre, par construction."""

    assistant: str = Field(pattern=IDENT_ASSISTANT)
    version: int = Field(ge=1)
    empreinte: str = Field(pattern=r"^[0-9a-f]{64}$")
    canal: Canal
    planificateur: NomPlanificateur
    consigne: str | None = None
    score_consigne: float | None = None
    reponse_fiable: bool = False
    a_valider: bool = False
    valide: bool | None = None
    sources_ignorees: int = Field(default=0, ge=0)
    etapes: list[JournalEtape] = Field(default_factory=list)
    duree_ms: int = Field(ge=0)
    fusion: Literal["rrf"] = "rrf"
    #: Exactement l'un des deux, comme `evenement` : un condensé de personne, ou un robot.
    auteur_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{16,64}$")
    robot: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _un_seul_auteur(self):
        if (self.auteur_hash is None) == (self.robot is None):
            raise ValueError("un journal a soit un auteur (condensé), soit un robot")
        return self


# ─── Canonicalisation ────────────────────────────────────────────────────────────────────────


def canonique(fiche: FicheAssistant) -> str:
    """Le texte canonique d'une fiche : clés triées, sans espace, listes dans leur ordre (le rang
    des sources et l'ordre des consignes sont du contenu). Hors : `publication` (où l'assistant
    est servi n'est pas ce qu'il fait) et `reference` (dérivé)."""
    contenu = fiche.model_dump(mode="json", exclude={"publication", "reference"})
    return json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def empreinte(contenu_canonique: str) -> str:
    return hashlib.sha256(contenu_canonique.encode("utf-8")).hexdigest()


# ─── Projection sur le contrat de recherche v1 ───────────────────────────────────────────────


def vers_resultats_v1(
    passages: Sequence[Passage],
    *,
    extrait: Callable[[str], str],
    surlignages: Callable[[str], list[list[int]]],
    titres: dict[str, str],
    droit: Callable[[str], str],
    passages_max: int = 3,
) -> list[dict]:
    """Les passages projetés sur `results[]` de GET /api/v1/search, sans perte : groupés par
    document dans l'ordre d'arrivée, au plus `passages_max` extraits par document, score = le
    meilleur. `extrait` et `surlignages` sont ceux de la recherche (ils dépendent de la question),
    `titres[source]` le titre de la collection, `droit(source)` le droit de la personne."""
    resultats: dict[tuple[str, str], dict] = {}
    for p in passages:
        cle = (p.source, p.document)
        r = resultats.get(cle)
        if r is None:
            r = resultats[cle] = {
                "id": f"{p.source}:{p.document}",
                "title": p.titre or p.document,
                "date": p.date.isoformat() if p.date else None,
                "url": p.url,
                "score": p.score,
                "hits": [],
                "context": {"collection": {"id": p.source, "title": titres.get(p.source, p.source)}, "right": droit(p.source)},
            }
        if len(r["hits"]) >= passages_max:
            continue
        if p.score is not None and (r["score"] is None or p.score > r["score"]):
            r["score"] = p.score
        e = extrait(p.texte)
        r["hits"].append(
            {
                "snippet": e,
                "highlights": surlignages(e),
                "field": "content",
                "location": {"start_seconds": None, "end_seconds": None, "page": p.page},
                "speaker": None,
                "url": p.url or r["url"],
            }
        )
    sortie = []
    for r in resultats.values():
        if not r["url"]:
            r["url"] = next((h["url"] for h in r["hits"] if h["url"]), None)
        sortie.append(r)
    return sortie
