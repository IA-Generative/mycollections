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
import time

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas.embeddings.base import LangchainEmbeddingsWrapper
from ragas.llms.base import LangchainLLMWrapper

from app.config import settings
from app.generation import fournisseur
from app.generation.resultats import MARQUE_REPARATION, Compteurs, Debit, _usage  # noqa: F401 — réexportés


class LLMCompte(LangchainLLMWrapper):
    """L'enveloppe ragas d'un modèle LangChain, qui compte chaque appel et appelle en synchrone."""

    def __init__(self, langchain_llm, compteurs: Compteurs, debit: Debit | None = None, **kw):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            super().__init__(langchain_llm, **kw)
        self.compteurs = compteurs
        self.debit = debit or Debit(0)

    def generate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None):
        self.debit.prendre()
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

    def __init__(self, embeddings, compteurs: Compteurs, debit: Debit | None = None, **kw):
        super().__init__(embeddings, **kw)
        self.compteurs = compteurs
        self.debit = debit or Debit(0)

    def embed_query(self, text):
        self.debit.prendre()
        self.compteurs.compter_embeddings()
        return super().embed_query(text)

    def embed_documents(self, texts):
        self.debit.prendre()
        self.compteurs.compter_embeddings()
        return super().embed_documents(texts)

    async def aembed_query(self, text):
        return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts):
        return await asyncio.to_thread(self.embed_documents, texts)


def fabriquer_llm(compteurs: Compteurs, *, url: str | None = None, cle: str | None = None, modele: str | None = None, run_config=None, debit: Debit | None = None) -> LLMCompte:
    if url is None and cle is None:  # fournisseur du service : passerelle dédiée ou repli OpenRAG
        f = fournisseur()
        url, cle = f.url, f.cle
    chat = ChatOpenAI(
        base_url=url or settings.generation_llm_url,
        api_key=cle or settings.generation_llm_cle,
        model=modele or settings.generation_llm_modele,
        max_tokens=settings.generation_max_tokens,
        temperature=0.1,
        timeout=settings.generation_delai_appel_s,
        max_retries=0,  # ragas fait ses propres réessais (RunConfig.max_retries), visibles au compteur
    )
    return LLMCompte(chat, compteurs, debit=debit, run_config=run_config)


def fabriquer_embeddings(
    compteurs: Compteurs, *, url: str | None = None, cle: str | None = None, modele: str | None = None, run_config=None, debit: Debit | None = None
) -> EmbeddingsComptes:
    f = fournisseur()  # même fournisseur que le modèle de rédaction
    emb = OpenAIEmbeddings(
        base_url=url or settings.generation_embeddings_url or f.url,
        api_key=cle or f.cle,
        model=modele or settings.generation_embeddings_modele or "non-configure",
        check_embedding_ctx_length=False,  # texte brut : pas de découpage tiktoken, pas de téléchargement
        timeout=settings.generation_delai_appel_s,
        max_retries=0,
    )
    return EmbeddingsComptes(emb, compteurs, debit=debit, run_config=run_config)
