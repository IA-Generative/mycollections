"""« OWUI simulé » : un modèle de la passerelle qui appelle les outils du vrai `/mcp`, comme le fait
Open WebUI, avec le jeton du compte de test.

Les outils viennent de `tools/list` (rien n'est recopié ici) et passent au modèle en outils
OpenAI. Rien ne lui dit où chercher : il doit enchaîner `lister_sources`, éventuellement
`proposer_sources`, puis `rechercher`, et rédiger en citant les liens. La conversation est
enregistrée : appels d'outils (arguments, taille, assistant, passages rendus sans leur texte),
appels et jetons de modèle, durée.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from app.security_utils import neutralize_for_prompt, wrap_untrusted
from scripts.campagne.cible import Cible, ErreurMcp, Passerelle

MODELE = "tools-pro"
MAX_TOURS = 6
#: Ce que le modèle lit d'un résultat d'outil (le reste est coupé, comme le ferait un client).
TRONQUE = 12_000
SYSTEME = (
    "Tu es l'assistant conversationnel des agents d'un ministère. Tu disposes des outils de « Mes collections », "
    "un service de recherche dans des collections de documents. Quand une question demande des informations "
    "documentaires, utilise ces outils : trouve d'abord où chercher, puis cherche, puis réponds en français en "
    "t'appuyant uniquement sur les passages trouvés et en citant leurs liens. Si rien ne convient, dis-le."
)
#: Les modèles à raisonnement (tools-pro) dépensent leurs jetons à réfléchir avant d'écrire : à 120,
#: la question sortait vide (`finish_reason: length`) et le catalogue réel ne jouait rien.
MAX_TOKENS_QUESTION = 1000
CONSIGNE_QUESTION = (
    "On te donne un passage d'un document administratif. Écris UNE question, en français, qu'un agent poserait "
    "et à laquelle ce passage répond. Ne cite ni le titre du document ni le nom de la collection. Réponds par la "
    "question seule, sur une ligne."
)


def outils_openai(outils: list[dict]) -> list[dict]:
    """Les outils MCP (`tools/list`) en outils OpenAI."""
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}},
        }
        for t in outils
    ]


def corps_outil(resultat: dict) -> tuple[Any, bool]:
    """Le JSON rendu par un outil (premier contenu texte), et s'il s'agit d'une erreur d'outil."""
    erreur = bool(resultat.get("isError"))
    contenus = resultat.get("content") or []
    texte = next((c.get("text", "") for c in contenus if c.get("type") == "text"), "")
    try:
        return json.loads(texte), erreur
    except ValueError:
        return texte, erreur


def resumer(nom: str, args: dict, corps: Any, erreur: bool, octets: int) -> dict:
    """Une ligne de la trace : de quoi juger (assistant choisi, passages, collections lisibles), sans les textes."""
    ligne: dict[str, Any] = {"outil": nom, "args": args, "octets": octets}
    if erreur or not isinstance(corps, dict):
        ligne["erreur"] = str(corps)[:300]
        return ligne
    if nom == "lister_sources":
        ligne["assistants"] = {a.get("id"): [c.get("id") for c in a.get("collections") or []] for a in corps.get("assistants") or []}
    elif nom == "proposer_sources":
        ligne["assistant"] = corps.get("assistant")
        ligne["consigne"] = corps.get("consigne")
        ligne["proposees"] = [s.get("id") for s in corps.get("sources") or []]
    elif nom == "rechercher":
        plan = corps.get("plan") or {}
        ligne["assistant"] = plan.get("assistant") or args.get("assistant")
        ligne["consigne"] = plan.get("consigne")
        ligne["sources_plan"] = [s.get("id") for s in plan.get("sources") or []]
        ligne["passages"] = [
            {"rang": i, "collection": (p.get("collection") or {}).get("id"), "titre": (p.get("titre") or "")[:80], "url": p.get("url")}
            for i, p in enumerate(corps.get("passages") or [], start=1)
        ]
    return ligne


def textes_des_passages(texte: str) -> list[str]:
    """Les textes des passages rendus par `rechercher` : ce que le modèle a lu (pour le juge de fidélité)."""
    try:
        corps = json.loads(texte)
    except ValueError:
        return []
    if not isinstance(corps, dict):
        return []
    return [str(p.get("texte") or "") for p in corps.get("passages") or [] if isinstance(p, dict)]


class Agent:
    def __init__(self, cible: Cible, passerelle: Passerelle, *, modele: str = MODELE, max_tours: int = MAX_TOURS, horloge: Callable[[], float] = time.monotonic):
        self.cible, self.passerelle, self.modele, self.max_tours, self._horloge = cible, passerelle, modele, max_tours, horloge
        self._outils: list[dict] | None = None

    def outils(self) -> list[dict]:
        if self._outils is None:
            self._outils = outils_openai(self.cible.mcp("tools/list").get("tools") or [])
        return self._outils

    def _appeler_outil(self, nom: str, args: dict) -> tuple[str, dict]:
        try:
            resultat = self.cible.mcp("tools/call", {"name": nom, "arguments": args})
        except ErreurMcp as e:
            texte = json.dumps({"erreur": str(e)}, ensure_ascii=False)
            return texte, {"outil": nom, "args": args, "octets": len(texte), "erreur": str(e), "http": e.statut}
        corps, erreur = corps_outil(resultat)
        texte = corps if isinstance(corps, str) else json.dumps(corps, ensure_ascii=False)
        return texte, resumer(nom, args, corps, erreur, len(texte.encode()))

    def converser(self, question: str) -> dict:
        """Une conversation, jusqu'à la réponse ou `max_tours` tours de modèle."""
        outils = self.outils()
        messages: list[dict] = [{"role": "system", "content": SYSTEME}, {"role": "user", "content": question}]
        trace: list[dict] = []
        contexte: list[str] = []
        debut, appels = self._horloge(), 0
        for _ in range(self.max_tours):
            rep = self.passerelle.completer({"model": self.modele, "messages": messages, "tools": outils, "tool_choice": "auto", "temperature": 0})
            appels += 1
            m = (rep.get("choices") or [{}])[0].get("message") or {}
            messages.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls")})
            if not m.get("tool_calls"):
                return {
                    "question": question,
                    "trace": trace,
                    "contexte": contexte,
                    "reponse": m.get("content"),
                    "tours": appels,
                    "appels_modele": appels,
                    "duree_ms": self._ms(debut),
                }
            for tc in m["tool_calls"]:
                fonction = tc.get("function") or {}
                try:
                    args = json.loads(fonction.get("arguments") or "{}")
                except ValueError:
                    args = {}
                texte, ligne = self._appeler_outil(fonction.get("name", ""), args if isinstance(args, dict) else {})
                trace.append(ligne)
                if fonction.get("name") == "rechercher":
                    contexte += textes_des_passages(texte)
                messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": texte[:TRONQUE]})
        return {
            "question": question,
            "trace": trace,
            "contexte": contexte,
            "reponse": None,
            "tours": appels,
            "appels_modele": appels,
            "duree_ms": self._ms(debut),
            "arret": "trop de tours",
        }

    def ecrire_question(self, extrait: str) -> str | None:
        """Une question à laquelle ce passage répond (catalogue réel) ; le passage est une DONNÉE encadrée."""
        donnees = wrap_untrusted(neutralize_for_prompt(extrait, max_len=3000), label="PASSAGE")
        rep = self.passerelle.completer(
            {
                "model": self.modele,
                "messages": [{"role": "system", "content": CONSIGNE_QUESTION}, {"role": "user", "content": donnees}],
                "temperature": 0,
                "max_tokens": MAX_TOKENS_QUESTION,
            }
        )
        texte = ((rep.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ligne = " ".join(texte.split()).strip().strip('"«» ')
        return ligne[:300] or None

    def _ms(self, debut: float) -> int:
        return int((self._horloge() - debut) * 1000)
