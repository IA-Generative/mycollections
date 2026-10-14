"""Ce que la génération produit et compte, sans dépendre de ragas.

Le service et ses tests d'API importent ce module même quand l'extra « generation » n'est pas
installé ; `modele` et `moteur`, eux, importent ragas.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

#: L'instruction de `FixOutputFormat` : ragas renvoie au modèle une sortie qu'il n'a pas su lire.
#: La voir dans un prompt, c'est compter un JSON raté (exigence : ne pas masquer ces échecs).
MARQUE_REPARATION = "The output string did not satisfy the constraints given in the prompt"


@dataclass
class Compteurs:
    """Partagé entre le fil de ragas (qui écrit) et la boucle du service (qui lit) : sous verrou."""

    appels_llm: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    reparations_json: int = 0
    inachevees: int = 0
    erreurs_llm: int = 0
    refus_debit: int = 0
    appels_embeddings: int = 0
    duree_llm_s: float = 0.0
    phase: str = "lecture"
    _verrou: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def observer(self, prompt: str, resultat, duree: float, erreur: BaseException | None = None) -> None:
        entree, sortie, inachevee = _usage(resultat) if resultat is not None else (0, 0, False)
        with self._verrou:
            self.appels_llm += 1
            self.duree_llm_s += duree
            self.tokens_entree += entree
            self.tokens_sortie += sortie
            if MARQUE_REPARATION in prompt:
                self.reparations_json += 1
            if inachevee:
                self.inachevees += 1
            if erreur is not None:
                self.erreurs_llm += 1
                if "RateLimit" in type(erreur).__name__ or "429" in str(erreur)[:200]:
                    self.refus_debit += 1

    def compter_embeddings(self, n: int = 1) -> None:
        with self._verrou:
            self.appels_embeddings += n

    def poser_phase(self, phase: str) -> None:
        with self._verrou:
            self.phase = phase

    def instantane(self) -> dict:
        with self._verrou:
            return {
                "appels_llm": self.appels_llm,
                "tokens_entree": self.tokens_entree,
                "tokens_sortie": self.tokens_sortie,
                "reparations_json": self.reparations_json,
                "inachevees": self.inachevees,
                "erreurs_llm": self.erreurs_llm,
                "refus_debit": self.refus_debit,
                "appels_embeddings": self.appels_embeddings,
                "duree_llm_s": round(self.duree_llm_s, 1),
            }


class Debit:
    """Au plus `par_minute` appels sur toute fenêtre glissante de 60 s, tous fils confondus.
    `prendre()` bloque le fil appelant jusqu'à ce qu'une place se libère (les fils de ragas
    attendent ; la boucle du service, elle, n'est jamais bloquée). 0 = sans limite."""

    def __init__(self, par_minute: int, horloge=time.monotonic, dormir=time.sleep):
        self.par_minute = max(0, int(par_minute))
        self._horloge, self._dormir = horloge, dormir
        self._appels: deque[float] = deque()
        self._verrou = threading.Lock()
        self.attente_s = 0.0

    def prendre(self) -> None:
        if not self.par_minute:
            return
        while True:
            with self._verrou:
                maintenant = self._horloge()
                while self._appels and maintenant - self._appels[0] >= 60.0:
                    self._appels.popleft()
                if len(self._appels) < self.par_minute:
                    self._appels.append(maintenant)
                    return
                attente = 60.0 - (maintenant - self._appels[0]) + 0.05
                self.attente_s += attente
            self._dormir(attente)


def _usage(resultat) -> tuple[int, int, bool]:
    """(jetons d'entrée, jetons de sortie, coupée par la limite) d'un `LLMResult` LangChain."""
    usage = (getattr(resultat, "llm_output", None) or {}).get("token_usage") or {}
    entree = int(usage.get("prompt_tokens") or 0)
    sortie = int(usage.get("completion_tokens") or 0)
    inachevee = False
    for liste in getattr(resultat, "generations", None) or []:
        for g in liste:
            info = getattr(g, "generation_info", None) or {}
            message = getattr(g, "message", None)
            fin = info.get("finish_reason") or (getattr(message, "response_metadata", None) or {}).get("finish_reason")
            inachevee = inachevee or fin == "length"
            if not usage and message is not None and getattr(message, "usage_metadata", None):
                entree += int(message.usage_metadata.get("input_tokens") or 0)
                sortie += int(message.usage_metadata.get("output_tokens") or 0)
    return entree, sortie, inachevee


@dataclass(frozen=True)
class PersonaDemande:
    nom: str
    description_role: str


@dataclass
class PaireGeneree:
    question: str
    reponse: str
    contextes: list[dict]
    persona_nom: str
    synthetiseur: str
    style: str
    longueur: str

    @property
    def chunk_ids(self) -> list[str]:
        return [c["chunk_id"] for c in self.contextes if c.get("chunk_id")]


@dataclass
class ResultatGeneration:
    etat: str
    paires: list[PaireGeneree] = field(default_factory=list)
    paires_echouees: int = 0
    morceaux_envoyes: int = 0
    noeuds_avec_proprietes: int = 0
    duree_s: float = 0.0
    erreur: str | None = None


def message_sur(e: BaseException) -> str:
    """Ce qu'on dit d'une erreur : son genre, borné, sans le texte d'un passage."""
    nom = type(e).__name__
    if nom in ("APIConnectionError", "ConnectError", "ConnectTimeout", "APITimeoutError", "ReadTimeout"):
        return "Le modèle de langage ne répond pas (passerelle MirAI injoignable ou trop lente)."
    if nom in ("AuthenticationError", "PermissionDeniedError"):
        return "Le modèle de langage refuse la clé configurée (MYCOLLECTIONS_GENERATION_LLM_CLE)."
    if "RateLimit" in nom or "429" in str(e)[:200]:
        return "Le modèle de langage limite le débit : réessayez plus tard ou baissez le parallélisme."
    return f"{nom} : {str(e)[:200]}"
