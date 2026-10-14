"""Les modèles de la génération (passerelle MirAI, OpenAI-compatible) et leur compteur.

Deux choix, tous deux dictés par la façon dont ragas s'exécute :

- ragas enchaîne plusieurs `asyncio.run` dans un même run (extraction, puis scénarios, puis
  paires). Un client HTTP asynchrone qui garde ses connexions d'une boucle à l'autre échoue
  (« Event loop is closed »). Les appels passent donc par le client SYNCHRONE de LangChain, exécuté
  dans un fil (`asyncio.to_thread`) : indifférent aux boucles, et toujours parallèle.
- les extractions (une par passage) ne passent pas par les rappels de `generate()` de ragas : le
  coût se compte ici, à chaque appel, et non par le `token_usage_parser` de ragas.

Le compteur ne garde ni le texte des prompts ni celui des réponses : des nombres seulement.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas.embeddings.base import LangchainEmbeddingsWrapper
from ragas.llms.base import LangchainLLMWrapper

from app.config import settings

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

    def compter_embeddings(self, n: int = 1) -> None:
        with self._verrou:
            self.appels_embeddings += n

    def poser_phase(self, phase: str) -> None:
        with self._verrou:
            self.phase = phase

    def instantane(self) -> dict:
        with self._verrou:
            return {"appels_llm": self.appels_llm, "tokens_entree": self.tokens_entree,
                    "tokens_sortie": self.tokens_sortie, "reparations_json": self.reparations_json,
                    "inachevees": self.inachevees, "erreurs_llm": self.erreurs_llm,
                    "appels_embeddings": self.appels_embeddings, "duree_llm_s": round(self.duree_llm_s, 1)}


def _usage(resultat) -> tuple[int, int, bool]:
    """(jetons d'entrée, jetons de sortie, coupée par la limite) d'un `LLMResult` LangChain."""
    usage = ((getattr(resultat, "llm_output", None) or {}).get("token_usage") or {})
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


class LLMCompte(LangchainLLMWrapper):
    """L'enveloppe ragas d'un modèle LangChain, qui compte chaque appel et appelle en synchrone."""

    def __init__(self, langchain_llm, compteurs: Compteurs, **kw):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            super().__init__(langchain_llm, **kw)
        self.compteurs = compteurs

    def generate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None):
        debut = time.monotonic()
        texte = prompt.to_string() if hasattr(prompt, "to_string") else str(prompt)
        try:
            resultat = super().generate_text(prompt, n=n, temperature=temperature, stop=stop, callbacks=callbacks)
        except Exception as e:
            self.compteurs.observer(texte, None, time.monotonic() - debut, e)
            raise
        self.compteurs.observer(texte, resultat, time.monotonic() - debut)
        return resultat

    async def agenerate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None):
        return await asyncio.to_thread(self.generate_text, prompt, n, temperature, stop, callbacks)


class EmbeddingsComptes(LangchainEmbeddingsWrapper):
    """Même principe pour les embeddings (utilisés seulement par les personas automatiques)."""

    def __init__(self, embeddings, compteurs: Compteurs, **kw):
        super().__init__(embeddings, **kw)
        self.compteurs = compteurs

    def embed_query(self, text):
        self.compteurs.compter_embeddings()
        return super().embed_query(text)

    def embed_documents(self, texts):
        self.compteurs.compter_embeddings()
        return super().embed_documents(texts)

    async def aembed_query(self, text):
        return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts):
        return await asyncio.to_thread(self.embed_documents, texts)


def fabriquer_llm(compteurs: Compteurs, *, url: str | None = None, cle: str | None = None,
                  modele: str | None = None, run_config=None) -> LLMCompte:
    chat = ChatOpenAI(
        base_url=url or settings.generation_llm_url,
        api_key=cle or settings.generation_llm_cle,
        model=modele or settings.generation_llm_modele,
        max_tokens=settings.generation_max_tokens,
        temperature=0.1,
        timeout=settings.generation_delai_appel_s,
        max_retries=0,  # ragas fait ses propres réessais (RunConfig.max_retries), visibles au compteur
    )
    return LLMCompte(chat, compteurs, run_config=run_config)


def fabriquer_embeddings(compteurs: Compteurs, *, url: str | None = None, cle: str | None = None,
                         modele: str | None = None, run_config=None) -> EmbeddingsComptes:
    emb = OpenAIEmbeddings(
        base_url=url or settings.generation_embeddings_url or settings.generation_llm_url,
        api_key=cle or settings.generation_llm_cle,
        model=modele or settings.generation_embeddings_modele or "non-configure",
        check_embedding_ctx_length=False,  # texte brut : pas de découpage tiktoken, pas de téléchargement
        timeout=settings.generation_delai_appel_s,
        max_retries=0,
    )
    return EmbeddingsComptes(emb, compteurs, run_config=run_config)
