"""Répondre à une question posée à une collection, sans HTTP.

C'est le chemin du bac à sable (`POST /api/playground/{c}/chat`) : RAG d'OpenRAG, puis repli par
recherche quand le RAG ne rend aucune source, puis repli par les noms de fichiers pour au moins
décrire la collection. La mesure de qualité l'appelle question par question.

La mention « en cours de vérification » est rendue à part (`Reponse.mention`) : c'est au bac à
sable de l'afficher, pas à la mesure de la juger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.security_utils import neutralize_for_prompt, sanitize_oneline, wrap_untrusted
from app.services.sources_openrag import sources_de


class ErreurReponse(RuntimeError):
    """OpenRAG n'a pas pu répondre du tout (le RAG lui-même a échoué)."""


@dataclass
class Reponse:
    contenu: str
    sources: list = field(default_factory=list)
    source_names: list = field(default_factory=list)
    repli: str = "aucun"  # aucun | recherche | fichiers
    mention: str | None = None
    modele: str = ""
    system_prompt_used: bool = False

    @property
    def fallback_used(self) -> bool:
        return self.repli != "aucun"


async def repondre(collection: str, question: str, *, client, system_prompt: str = "", temperature: float = 0.1) -> Reponse:
    """La réponse de la collection à `question`. `client` : un OpenRAGClient (le bac à sable
    vérifie sa santé avant ; la mesure aussi, une fois pour toutes les questions)."""
    # Les aides vivent dans le routeur, où les tests existants les remplacent : lues à l'appel.
    from app.routers.playground import (
        _CHAT_MAX_TOKENS,
        _EXTRAIT_MAX_CARS,
        _get_collection_sample,
        _morceaux_par_recherche,
        relier_au_proxy,
        retirer_le_pied_sources,
        signer_les_liens_de_la_source,
        situer_source,
    )

    # Load collection system prompt if not overridden
    if not system_prompt:
        try:
            from app.services.collection_store import get_system_prompt

            prompt = await get_system_prompt(collection)
            if prompt:
                system_prompt = prompt
        except Exception:
            pass

    model = f"openrag-{collection}"

    # Step 1: Try normal RAG via OpenRAG chat completions
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": question})

    try:
        result = await client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=_CHAT_MAX_TOKENS,
        )
    except Exception as e:
        raise ErreurReponse(f"Erreur OpenRAG: {e}") from e

    # Extract response and sources
    content = ""
    sources = []
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")

    # `extra` : chaîne (OpenRAG 2.2.1) ou objet (2.3.1) ; sources ramenées à plat (2.3.1 : sous `chunk`).
    sources = sources_de(result.get("extra"))

    # Étape 2a : aucune source ? On cherche nous-mêmes avant d'abandonner.
    #
    # Le RAG d'OpenRAG écarte les morceaux sous son seuil de similarité : une
    # question posée par IDENTIFIANT NU (« NATINF 7987 », « département 69 »)
    # n'y survit pas, alors que /search classe le bon morceau en tête — mesuré
    # sur l'amorce NATINF (0 source par le chat, morceau exact en 1er par la
    # recherche). On rejoue donc la question en recherche et on injecte les
    # morceaux trouvés comme CONTEXTE, en donnée délimitée.
    fallback_used = False
    repli_recherche = False
    if not sources:
        morceaux = await _morceaux_par_recherche(client, collection, question)
        if morceaux:
            fallback_used = repli_recherche = True
            sources = morceaux
            extraits = wrap_untrusted(
                "\n\n---\n\n".join(neutralize_for_prompt(m.get("content") or "", max_len=_EXTRAIT_MAX_CARS) for m in morceaux),
                label="DOCUMENTS",
            )
            messages_repli = [
                {
                    "role": "system",
                    "content": (system_prompt + "\n\n" if system_prompt else "")
                    + ("Réponds à la question en te fondant UNIQUEMENT sur les documents fournis ci-dessous. Si la réponse ne s'y trouve pas, dis-le simplement."),
                },
                {"role": "user", "content": f"{extraits}\n\n{question}"},
            ]
            try:
                resultat_repli = await client.chat(
                    model=model,
                    messages=messages_repli,
                    temperature=temperature,
                    max_tokens=_CHAT_MAX_TOKENS,
                )
                if resultat_repli.get("choices"):
                    content = resultat_repli["choices"][0].get("message", {}).get("content", "") or content
            except Exception:  # noqa: BLE001 — le repli ne casse jamais la réponse
                pass

    # Étape 2b : toujours rien ? Les noms de fichiers, pour au moins décrire la collection.
    if not sources:
        sample_files = await _get_collection_sample(client, collection)
        if sample_files:
            fallback_used = True

            # Build context from file names and metadata. Les noms de fichiers
            # sont contrôlés à l'upload (non fiables) : on les neutralise et on
            # les passe en DONNÉE délimitée, jamais dans le prompt système.
            file_list = []
            for i, f in enumerate(sample_files, 1):
                fname = sanitize_oneline(f.get("original_filename") or f.get("filename") or f"fichier-{i}", max_len=200)
                fsize = sanitize_oneline(str(f.get("file_size", "")), max_len=20)
                file_list.append(f"- {fname} ({fsize})")
                sources.append(f)

            total_files_count = len(await client.list_files(collection))
            files_block = wrap_untrusted("\n".join(file_list), label="NOMS DE FICHIERS")

            fallback_system = (system_prompt + "\n\n" if system_prompt else "") + (
                f"Cette collection '{collection}' contient {total_files_count} documents indexes. "
                "Reponds a la question en te basant sur les noms de fichiers (fournis comme donnee) "
                "pour decrire le contenu de la collection."
            )

            fallback_messages = [
                {"role": "system", "content": fallback_system},
                {"role": "user", "content": f"{files_block}\n\n{question}"},
            ]

            try:
                fallback_result = await client.chat(
                    model=model,
                    messages=fallback_messages,
                    temperature=temperature,
                    max_tokens=_CHAT_MAX_TOKENS,
                )
                if "choices" in fallback_result and fallback_result["choices"]:
                    content = fallback_result["choices"][0].get("message", {}).get("content", "")
            except Exception:
                pass

    # Format source names
    source_names = []
    for s in sources:
        name = s.get("original_filename") or s.get("filename") or ""
        if name and name not in source_names:
            source_names.append(name)

    # Les liens que le modèle écrit lui-même dans la réponse (« Sources : … »)
    # visent l'API publique d'OpenRAG : ouverts dans le navigateur, ils passent par
    # le SSO d'OpenRAG puis finissent en « User does not have access to this
    # file ». On les ramène sur notre proxy, qui porte le jeton.
    content = relier_au_proxy(retirer_le_pied_sources(content))
    for s in sources:
        situer_source(s)
        signer_les_liens_de_la_source(s)

    # Règle 3 : une collection non publiée à tous répond avec la mention — rendue À PART : le
    # bac à sable la préfixe, la mesure de qualité ne doit pas la lire comme une partie de la réponse.
    mention = None
    try:
        from app.services.collectif_store import fiche
        from app.services.etats import mention_verification

        mention = mention_verification((await fiche(collection))["etat_collab"])
    except Exception:  # noqa: BLE001 — fiche absente : pas de mention, pas de panne
        mention = None

    return Reponse(
        contenu=content,
        sources=sources,
        source_names=source_names,
        repli="recherche" if repli_recherche else ("fichiers" if fallback_used else "aucun"),
        mention=mention,
        modele=model,
        system_prompt_used=bool(system_prompt),
    )
