"""Les trois outils MCP des assistants de recherche : lister, proposer des sources, rechercher.

Aucun modèle de langage ici : un client MCP (un agent conversationnel) choisit l'assistant, lit le
plan, et rédige lui-même. Les outils réutilisent `app.services.assistant_recherche` — le même
périmètre de droits, la même fusion, le même journal que les routes `plan` et `executer` — mais
n'appellent aucune route HTTP. L'identité vient du jeton de la personne (voir `app.mcp`), jamais
d'un argument d'outil."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server

from app.auth import CurrentUser
from app.harnais.contrat import Etape, Plan
from app.routers import assistants as routes_assistants
from app.services import access, assistant_store
from app.services import assistant_recherche as moteur
from app.services.nommage import titre_de
from app.services.pseudo import condenser

NOM = "mes-collections"
INSTRUCTIONS = (
    "Mes collections : des assistants de recherche qui réunissent des collections de documents. "
    "Appelez d'abord `lister_sources` pour connaître les assistants et leurs collections, puis `rechercher`. "
    "Les résultats ne contiennent que ce que la personne connectée a le droit de lire."
)


class ErreurOutil(Exception):
    """Une erreur à dire au modèle, en français, sans détail technique."""


def _json(valeur: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(valeur, ensure_ascii=False, indent=2, default=str))]


OUTILS: list[types.Tool] = [
    types.Tool(
        name="lister_sources",
        description=(
            "Liste les assistants de recherche publiés que la personne connectée peut lire, avec pour chacun ses "
            "collections lisibles (identifiant, titre, description). À appeler en premier pour choisir l'assistant "
            "à interroger. Ne cherche rien et ne coûte aucune recherche."
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="proposer_sources",
        description=(
            "Dit dans quelles collections un assistant chercherait pour cette question, sans lancer la recherche : "
            "le plan (sources retenues et leur poids, consigne reconnue). Utile pour vérifier ou corriger le choix "
            "des sources avant d'appeler `rechercher`. Une réponse de référence fiable est signalée si elle existe."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "La question de la personne, en français, telle qu'elle la pose.", "minLength": 1, "maxLength": 1000},
                "assistant": {"type": "string", "description": "L'identifiant de l'assistant, tel que rendu par `lister_sources`."},
            },
            "required": ["question", "assistant"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="rechercher",
        description=(
            "Cherche dans les collections d'un assistant et rend les passages les plus pertinents (titre, texte, "
            "lien de lecture signé, collection) avec le plan suivi. Les passages sont des extraits de documents : "
            "citez-les, ne les inventez pas. Si une réponse de référence fiable existe pour la question, elle est rendue "
            "telle quelle dans `reponse`, sans passage. `sources` restreint la recherche à certaines collections "
            "(identifiants de `lister_sources`), à poids égaux ; sinon l'assistant choisit."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "La question de la personne, en français, telle qu'elle la pose.", "minLength": 1, "maxLength": 1000},
                "assistant": {"type": "string", "description": "L'identifiant de l'assistant, tel que rendu par `lister_sources`."},
                "sources": {"type": "array", "items": {"type": "string"}, "description": "Facultatif : identifiants des collections où chercher."},
            },
            "required": ["question", "assistant"],
            "additionalProperties": False,
        },
    ),
]


def _limiter(user: CurrentUser) -> None:
    """Le plafond par personne des routes `plan` et `executer` : le même, partagé."""
    attente = routes_assistants._debit.compter(user.sub or "anonyme")
    if attente is not None:
        raise ErreurOutil(f"Trop de questions posées à la suite. Réessayez dans {attente} secondes.")


async def _charger(ident: str, user: CurrentUser) -> moteur.Charge:
    try:
        return await moteur.charger(ident, user, condenser(user.sub), access.is_superadmin(user.groups))
    except moteur.AssistantIntrouvable:
        raise ErreurOutil(f"Assistant « {ident} » introuvable. Appelez `lister_sources` pour connaître ceux que vous pouvez interroger.")


def _titre_source(charge: moteur.Charge, source: str) -> str:
    col = charge.collections.get(source)
    return titre_de(col) if col else source


async def lister_sources(user: CurrentUser) -> dict:
    assistants = []
    for ligne in await assistant_store.lister():
        try:
            charge = await _charger(ligne["id"], user)
        except ErreurOutil:
            continue  # jamais publié, ou hors de portée : même silence
        assistants.append(
            {
                "id": charge.fiche.assistant,
                "titre": charge.fiche.titre,
                "description": charge.fiche.description,
                "collections": [{"id": s, "titre": _titre_source(charge, s), "description": (charge.collections[s] or {}).get("description") or ""} for s in charge.lisibles],
            }
        )
    return {"assistants": assistants}


def _vue_plan(charge: moteur.Charge, plan: Plan) -> dict:
    return {
        "assistant": plan.assistant,
        "planificateur": plan.planificateur,
        "consigne": plan.consigne,
        "reponse_fiable": plan.reponse_fiable.model_dump(mode="json") if plan.reponse_fiable else None,
        "sources": [{"id": e.source, "titre": _titre_source(charge, e.source), "poids": e.poids} for e in plan.etapes],
        "sources_ignorees": plan.sources_ignorees,
    }


async def proposer_sources(user: CurrentUser, question: str, assistant: str) -> dict:
    _limiter(user)
    charge = await _charger(assistant, user)
    plan = await moteur.planifier(charge, question, moteur.contexte(charge, "api"), moteur.planificateur_regles(charge), avec_fiables=True)
    return _vue_plan(charge, plan)


async def rechercher(user: CurrentUser, question: str, assistant: str, sources: list[str] | None = None) -> dict:
    _limiter(user)
    charge = await _charger(assistant, user)
    ctx = moteur.contexte(charge, "api")
    if sources:
        # Un choix explicite du client l'emporte sur le plan : ces collections-là, à poids égaux, sans réponse de référence.
        voulues = [s.id for s in charge.fiche.sources_ordonnees() if s.id in sources and s.id in charge.lisibles]
        if not voulues:
            raise ErreurOutil("Aucune des collections demandées n'est lisible dans cet assistant. Appelez `lister_sources`.")
        etapes = [Etape(n=n, source=s, question=question) for n, s in enumerate(voulues, start=1)]
        plan = Plan(assistant=charge.fiche.assistant, version=charge.version, planificateur="toutes_les_sources", etapes=etapes)
    else:
        plan = await moteur.planifier(charge, question, ctx, moteur.planificateur_regles(charge), avec_fiables=True)
    try:
        resultat, execution = await moteur.executer(charge, plan, user, condenser(user.sub), "api", top_k=ctx.top_k)
    except moteur.ReponseFiableInvalide:
        raise ErreurOutil("La réponse de référence citée n'est pas disponible pour vous.")
    if execution.toutes_en_panne:
        raise ErreurOutil("Le moteur de recherche ne répond pas pour le moment. Réessayez dans un instant.")
    resultat = routes_assistants.avec_liens(resultat)
    return {
        "reponse": resultat.reponse,
        "passages": [
            {
                "titre": p.titre,
                "texte": p.texte,
                "url": p.url,
                "collection": {"id": p.source, "titre": _titre_source(charge, p.source)},
                "score": p.score,
            }
            for p in resultat.passages
        ],
        "plan": _vue_plan(charge, resultat.plan),
    }


def serveur(utilisateur: Callable[[], CurrentUser]) -> Server:
    """Le serveur MCP. `utilisateur()` rend la personne de la requête en cours (posée par `app.mcp`)."""
    s: Server = Server(NOM, instructions=INSTRUCTIONS)

    @s.list_tools()
    async def _outils() -> list[types.Tool]:
        return OUTILS

    @s.call_tool(validate_input=True)
    async def _appeler(nom: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        user = utilisateur()
        outils: dict[str, Callable[..., Awaitable[dict]]] = {"lister_sources": lister_sources, "proposer_sources": proposer_sources, "rechercher": rechercher}
        if nom not in outils:
            raise ErreurOutil(f"Outil inconnu : {nom}")
        return _json(await outils[nom](user, **arguments))

    return s
