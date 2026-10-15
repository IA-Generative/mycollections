"""Le juge : un appel au modèle de la génération, qui compare la réponse obtenue à la réponse
de référence et rend `{"verdict": "conforme|partiel|non_conforme", "justification": "…"}`.

Sans ragas : un appel OpenAI-compatible direct (httpx), au même fournisseur que la génération
(passerelle dédiée, ou repli sur le /v1 d'OpenRAG). Les trois textes sont des DONNÉES encadrées :
une réponse obtenue ne doit pas pouvoir dicter son verdict. Le débit est celui du processus
(`services.debit.partage`), partagé avec la génération.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.generation.resultats import Compteurs
from app.security_utils import neutralize_for_prompt, wrap_untrusted

VERDICTS_JUGE = ("conforme", "partiel", "non_conforme")

CONSIGNE = """Tu évalues la réponse d'un assistant documentaire d'un ministère.
Compare la RÉPONSE OBTENUE à la RÉPONSE DE RÉFÉRENCE, pour la QUESTION posée.
- conforme : mêmes faits essentiels, rien de contradictoire (la formulation peut différer) ;
- partiel : en partie juste, mais il manque un élément important de la référence ;
- non_conforme : contredit la référence, ou ne répond pas à la question.
Réponds UNIQUEMENT par un JSON : {"verdict": "conforme" | "partiel" | "non_conforme", "justification": "une phrase en français"}"""


class JugeIndisponible(RuntimeError):
    """Le modèle ne répond pas ou refuse : la mesure se replie sur la similarité."""


@dataclass
class Jugement:
    verdict: str
    justification: str


def construire_messages(question: str, reference: str, obtenue: str) -> list[dict]:
    donnees = (
        f"QUESTION :\n{neutralize_for_prompt(question, max_len=2000)}\n\n"
        f"RÉPONSE DE RÉFÉRENCE :\n{neutralize_for_prompt(reference, max_len=4000)}\n\n"
        f"RÉPONSE OBTENUE :\n{neutralize_for_prompt(obtenue, max_len=4000)}"
    )
    return [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": wrap_untrusted(donnees, label="TEXTES À COMPARER")}]


def lire_jugement(texte: str) -> Jugement:
    """Le JSON du juge, toléré entre balises de code ; ValueError s'il est illisible."""
    t = (texte or "").strip()
    bloc = re.search(r"```(?:json)?\s*(.*?)```", t, flags=re.S)
    if bloc:
        t = bloc.group(1)
    debut, fin = t.find("{"), t.rfind("}")
    if debut < 0 or fin <= debut:
        raise ValueError("pas de JSON")
    d = json.loads(t[debut : fin + 1])
    verdict = str(d.get("verdict") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if verdict not in VERDICTS_JUGE:
        raise ValueError(f"verdict inconnu : {verdict!r}")
    return Jugement(verdict, " ".join(str(d.get("justification") or "").split())[:500])


async def _appeler(messages: list[dict]) -> dict:
    from app.generation import fournisseur

    f = fournisseur()
    modele = settings.mesure_juge_modele or settings.generation_llm_modele
    corps = {"model": modele, "messages": messages, "temperature": 0, "max_tokens": 400}
    async with httpx.AsyncClient(timeout=settings.mesure_delai_appel_s) as client:
        r = await client.post(f"{f.url.rstrip('/')}/chat/completions", json=corps, headers={"Authorization": f"Bearer {f.cle}"})
        r.raise_for_status()
        return r.json()


async def juger(question: str, reference: str, obtenue: str, *, compteurs: Compteurs, debit=None) -> Jugement:
    """Un jugement ; une réparation si le JSON est illisible ; JugeIndisponible si le modèle
    ne répond pas (réseau, refus, quota)."""
    messages = construire_messages(question, reference, obtenue)
    for essai in range(2):
        if debit is not None:
            await asyncio.to_thread(debit.prendre)
        try:
            data = await _appeler(messages)
        except Exception as e:  # noqa: BLE001
            compteurs.observer("", None, 0.0, e)
            raise JugeIndisponible(type(e).__name__) from e
        usage = data.get("usage") or {}
        with compteurs._verrou:  # noqa: SLF001 — mêmes compteurs que la génération
            compteurs.appels_llm += 1
            compteurs.tokens_entree += int(usage.get("prompt_tokens") or 0)
            compteurs.tokens_sortie += int(usage.get("completion_tokens") or 0)
        texte = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        try:
            return lire_jugement(texte)
        except ValueError:
            if essai == 0:
                with compteurs._verrou:  # noqa: SLF001
                    compteurs.reparations_json += 1
                messages = messages + [
                    {"role": "assistant", "content": texte[:2000]},
                    {"role": "user", "content": 'Réponds UNIQUEMENT par le JSON demandé : {"verdict": …, "justification": …}'},
                ]
                continue
            raise
    raise ValueError("jugement illisible")
