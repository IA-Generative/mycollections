"""Les quatre outils MCP des assistants de recherche : trouver où chercher, lister, proposer des sources, rechercher.

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
from app.harnais.contrat import QUAND_TOUJOURS, Etape, Plan
from app.routers import assistants as routes_assistants
from app.services import access, assistant_store
from app.services import assistant_recherche as moteur
from app.services.nommage import titre_de
from app.services.pseudo import condenser

NOM = "mes-collections"
INSTRUCTIONS = (
    "Mes collections : des assistants de recherche qui réunissent des collections de documents, et les collections "
    "elles-mêmes. Pour savoir où chercher, appelez d'abord `trouver_collections` avec la question (ou `lister_sources` "
    "pour tout voir), puis `rechercher`. "
    "Les résultats ne contiennent que ce que la personne connectée a le droit de lire."
)


class ErreurOutil(Exception):
    """Une erreur à dire au modèle, en français, sans détail technique."""


def _json(valeur: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(valeur, ensure_ascii=False, indent=2, default=str))]


#: Passages rendus par défaut, et au plus : le moteur en fusionne jusqu'à 20, mais 20 passages en texte
#: intégral (28 à 45 Ko) remplissent la fenêtre d'un agent conversationnel. On ne coupe que la liste rendue.
LIMITE_DEFAUT = 8
LIMITE_MAX = 20
#: Longueur rendue du texte d'un passage ; la suite se lit par son lien signé.
TEXTE_MAX = 1200
CONSIGNE_DE_CITATION = (
    "Réponds uniquement à partir des passages ; cite chaque passage utilisé par son lien `url` (format Markdown [titre](url)) ; si aucun passage ne répond, dis-le."
)

#: Sources rendues par `trouver_collections`, par défaut et au plus.
TROUVER_DEFAUT = 5
TROUVER_MAX = 10

OUTILS: list[types.Tool] = [
    types.Tool(
        name="trouver_collections",
        description=(
            "À appeler en premier quand on ne sait pas où chercher. Classe, pour cette question, les assistants et les "
            "collections que la personne connectée peut interroger, du plus proche au moins proche (titre, description, "
            "cas traités), et rend les premiers avec leur `score`. Passez ensuite l'`id` du premier à `rechercher` ; si ses "
            "passages ne répondent pas, essayez le suivant. Une liste vide : rien ne ressemble à la question, voyez "
            "`lister_sources`. Ne cherche rien dans les documents et ne compte pas dans le quota de questions."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "La question de la personne, en français, telle qu'elle la pose.", "minLength": 1, "maxLength": 1000},
                "limite": {
                    "type": "integer",
                    "default": TROUVER_DEFAUT,
                    "description": f"Facultatif : nombre de sources rendues, de 1 à {TROUVER_MAX} ({TROUVER_DEFAUT} par défaut).",
                },
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="lister_sources",
        description=(
            "Pour tout voir (sinon `trouver_collections` choisit pour une question). Rend les assistants de recherche que la personne connectée "
            "peut interroger, et pour chacun ses collections de documents (identifiant, titre, description) et les cas "
            "qu'il sait traiter (`consignes`). Chaque collection qu'elle lit y figure aussi seule, sous son identifiant : "
            "s'interroge de la même façon. Quand un assistant a une consigne qui correspond à la question, "
            "préférez-le à une collection seule : il cherche dans l'ordre prévu et enchaîne ses sources. "
            "Ne cherche rien dans les documents et ne compte pas dans le quota de questions."
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="proposer_sources",
        description=(
            "Facultatif. Dit dans quelles collections un assistant chercherait pour cette question, sans chercher : "
            "les collections retenues et leur poids, la consigne reconnue, et une réponse de référence fiable si elle "
            "existe. Sert à vérifier le choix avant `rechercher` ; on peut aussi appeler `rechercher` directement."
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
            "Cherche dans les collections d'un assistant et rend les passages les plus pertinents : titre, début du "
            "texte, lien de lecture `url` (le texte complet s'y lit), collection. " + CONSIGNE_DE_CITATION + " "
            "Si une réponse de référence fiable existe, elle est rendue telle quelle dans `reponse`, sans passage. "
            "`sources` restreint la recherche à certaines collections (identifiants de `lister_sources`), à poids "
            f"égaux ; sinon l'assistant choisit. `limite` : nombre de passages rendus ({LIMITE_DEFAUT} par défaut, {LIMITE_MAX} au plus)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "La question de la personne, en français, telle qu'elle la pose.", "minLength": 1, "maxLength": 1000},
                "assistant": {"type": "string", "description": "L'identifiant de l'assistant, tel que rendu par `lister_sources`."},
                "sources": {"type": "array", "items": {"type": "string"}, "description": "Facultatif : identifiants des collections où chercher."},
                "limite": {
                    "type": "integer",
                    "default": LIMITE_DEFAUT,
                    "description": f"Facultatif : nombre de passages rendus, de 1 à {LIMITE_MAX} ({LIMITE_DEFAUT} par défaut ; au-delà de {LIMITE_MAX}, {LIMITE_MAX}).",
                },
            },
            "required": ["question", "assistant"],
            "additionalProperties": False,
        },
    ),
]


def _extrait(texte: str, longueur: int) -> str:
    """Le début du texte, coupé sur un espace et suivi de « … » quand il a été coupé."""
    if len(texte) <= longueur:
        return texte
    coupe = texte[:longueur]
    espace = coupe.rfind(" ")
    if espace > longueur // 2:  # sinon un mot démesuré (une adresse) : on coupe dedans plutôt que de tout perdre
        coupe = coupe[:espace]
    return coupe.rstrip() + "…"


def _limiter(user: CurrentUser) -> None:
    """Le plafond par personne des routes `plan` et `executer` : le même, partagé."""
    attente = routes_assistants._debit.compter(user.sub or "anonyme")
    if attente is not None:
        raise ErreurOutil(f"Trop de questions posées à la suite. Réessayez dans {attente} secondes.")


async def _collections_lisibles(user: CurrentUser) -> list[dict]:
    """Celles que la recherche propose à la personne (`/api/v1/search/scopes`) : même règle de
    lecture, même plafond de sensibilité."""
    from app.routers.recherche import _collections_lisibles as lisibles

    return await lisibles(user)


async def _charger_collection(ident: str, user: CurrentUser) -> moteur.Charge | None:
    """Une collection lisible servie seule, si `ident` la désigne et qu'aucun autre assistant ne porte ce nom."""
    ligne = await assistant_store.lire(ident)
    for col in await _collections_lisibles(user):
        if assistant_store.deriver_identifiant(col["name"]) == ident and (ligne is None or ligne.get("collection_name") == col["name"]):
            return moteur.charge_collection(col, user)
    return None


async def _charger(ident: str, user: CurrentUser) -> moteur.Charge:
    try:
        return await moteur.charger(ident, user, condenser(user.sub), access.is_superadmin(user.groups))
    except moteur.AssistantIntrouvable:
        charge = await _charger_collection(ident, user)
        if charge is not None:
            return charge
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
                # Les cas prévus par la fiche (« quand ») : ce qui distingue un assistant métier du miroir d'une collection.
                "consignes": [c.quand for c in charge.fiche.consignes if c.quand != QUAND_TOUJOURS],
            }
        )
    # Les collections que la personne lit sans assistant pour les porter seules (non publiées : amorces,
    # collections d'équipe) : la recherche les lui propose, « je ne sais pas où chercher » doit les trouver aussi.
    portees = {a["collections"][0]["id"] for a in assistants if len(a["collections"]) == 1}
    pris = {ligne["id"]: ligne.get("collection_name") for ligne in await assistant_store.lister(archives=True)}
    for col in await _collections_lisibles(user):
        ident = assistant_store.deriver_identifiant(col["name"])
        if col["name"] in portees or pris.get(ident, col["name"]) != col["name"]:
            continue  # déjà portée seule, ou identifiant pris par un autre assistant
        charge = moteur.charge_collection(col, user)
        assistants.append(
            {
                "id": ident,
                "titre": charge.fiche.titre,
                "description": charge.fiche.description,
                "collections": [{"id": col["name"], "titre": _titre_source(charge, col["name"]), "description": col.get("description") or ""}],
                "consignes": [],
            }
        )
    return {"assistants": assistants}


def _texte_de(entree: dict) -> str:
    """Ce qui décrit une entrée de `lister_sources` : titres, descriptions, cas traités."""
    morceaux = [entree["titre"], entree["description"], *entree["consignes"]]
    for c in entree["collections"]:
        morceaux += [c["titre"], c["description"]]
    return " ".join(m for m in dict.fromkeys(morceaux) if m)  # un miroir répète le titre de sa collection


async def trouver_collections(user: CurrentUser, question: str, limite: int = TROUVER_DEFAUT) -> dict:
    """Les entrées de `lister_sources` classées par ressemblance à la question (`moteur.apparieur_catalogue` :
    embeddings s'ils sont configurés, sinon sac de mots). Sans ressemblance, rien."""
    limite = max(1, min(TROUVER_MAX, limite))
    entrees = {a["id"]: a for a in (await lister_sources(user))["assistants"]}
    classes = await moteur.apparieur_catalogue().apparier(question, [(ident, _texte_de(a)) for ident, a in entrees.items()])
    return {"sources": [{**entrees[ident], "score": score} for ident, score in classes[:limite] if score > 0]}


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


async def rechercher(user: CurrentUser, question: str, assistant: str, sources: list[str] | None = None, limite: int = LIMITE_DEFAUT) -> dict:
    _limiter(user)
    limite = max(1, min(LIMITE_MAX, limite))
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
    # Après la fusion et le filtre de droits : on ne coupe que la liste rendue au client, jamais le moteur.
    resultat = routes_assistants.avec_liens(resultat.model_copy(update={"passages": resultat.passages[:limite]}))
    return {
        "reponse": resultat.reponse,
        "consigne_de_citation": CONSIGNE_DE_CITATION,
        "passages": [
            {
                "titre": p.titre,
                "texte": _extrait(p.texte, TEXTE_MAX),
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
        outils: dict[str, Callable[..., Awaitable[dict]]] = {
            "trouver_collections": trouver_collections,
            "lister_sources": lister_sources,
            "proposer_sources": proposer_sources,
            "rechercher": rechercher,
        }
        if nom not in outils:
            raise ErreurOutil(f"Outil inconnu : {nom}")
        return _json(await outils[nom](user, **arguments))

    return s
