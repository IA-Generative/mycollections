"""Playground router — quick RAG test for a collection."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser, current_user
from app.services import accueil
from app.services.openrag_client import OpenRAGClient
from app.security_utils import neutralize_for_prompt, sanitize_oneline, wrap_untrusted

router = APIRouter(prefix="/api/playground", tags=["Playground"])

# Les modèles RAG d'OpenRAG sont des modèles « à raisonnement » : ils émettent
# d'abord un reasoning_content (chaîne de pensée), puis la réponse dans content.
# Avec la limite par défaut (~1024 tokens), le raisonnement épuise le budget et
# content ressort VIDE (finish_reason=length) -> réponses vides côté playground
# et faux KO à l'évaluation. On donne donc une marge confortable.
_CHAT_MAX_TOKENS = 4096


# Questions hors-sujet ajoutées à tout jeu généré : vérifient que le RAG refuse
# de fabriquer une réponse quand le sujet n'est pas couvert.
_OUT_OF_SCOPE = [
    {"id": "hors-sujet-1", "question": "Quel est l'age du capitaine ?",
     "expected_answer": "", "must_cite": [], "tags": ["hors-sujet"], "out_of_scope": True,
     "note": "Question hors-sujet pour verifier que le RAG ne fabrique pas de reponse."},
    {"id": "hors-sujet-2", "question": "Quelle est la capitale de la Mongolie ?",
     "expected_answer": "", "must_cite": [], "tags": ["hors-sujet"], "out_of_scope": True,
     "note": "Question hors-sujet pour verifier que le RAG ne fabrique pas de reponse."},
]


def _parse_question_lines(text: str, limit: int = 8) -> list[dict]:
    """Parse une réponse « une question par ligne » en questions d'éval (léger).

    Réplique l'extraction robuste de useBank.generate() côté front : les modèles
    RAG produisent fiablement une liste de questions en texte, là où un prompt
    JSON exigeant renvoie souvent du vide.
    """
    questions: list[dict] = []
    for line in (text or "").split("\n"):
        q = re.sub(r"^[\s\-\*\d.\)•>]+", "", line)
        q = re.sub(r"[\s—-]+$", "", q).strip()
        if len(q) > 5 and "?" in q:
            questions.append({
                "id": f"q{len(questions) + 1}", "question": q,
                "expected_answer": "", "must_cite": [], "tags": [],
            })
            if len(questions) >= limit:
                break
    return questions


async def _generate_questions_via_lines(client: OpenRAGClient, model: str) -> list[dict]:
    """Fallback robuste : demande N questions une par ligne, puis les parse."""
    prompt = (
        "Propose 8 questions variees qu'un utilisateur pourrait poser sur le "
        "contenu indexe de cette collection, pour tester le RAG. Reponds "
        "UNIQUEMENT avec les questions, une par ligne, sans numerotation, sans "
        "puces, sans introduction ni conclusion. Chaque question doit etre "
        "specifique au contenu reel."
    )
    try:
        result = await client.chat(
            model=model, messages=[{"role": "user", "content": prompt}],
            temperature=0.4, max_tokens=_CHAT_MAX_TOKENS,
        )
    except Exception:
        return []
    content = ""
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")
    return _parse_question_lines(content)


class PlaygroundChatRequest(BaseModel):
    question: str
    system_prompt: str = ""
    top_k: int = 5
    temperature: float = 0.1


#: Ce qu'on garde d'un morceau injecté en contexte : de quoi répondre sans noyer
#: le modèle ni faire exploser la fenêtre quand cinq morceaux arrivent ensemble.
_EXTRAIT_MAX_CARS = 2000


async def _morceaux_par_recherche(
    client: OpenRAGClient, collection: str, question: str, top_k: int = 5
) -> list[dict]:
    """Les morceaux les plus proches de la question, au format « source » du chat.

    Le RAG du chat rend parfois zéro source là où la recherche trouve le bon
    morceau : c'est notre seconde chance, et elle rend de VRAIES sources — les
    puces et leurs liens marchent comme après une réponse ordinaire.
    """
    try:
        resultat = await client.search(collection, question, top_k=top_k)
    except Exception:  # noqa: BLE001 — pas de recherche, pas de repli : on continue
        return []
    morceaux = []
    for d in (resultat or {}).get("documents") or []:
        metadonnees = d.get("metadata") or {}
        contenu = d.get("content") or metadonnees.get("content") or ""
        if not contenu:
            continue
        morceaux.append({**{k: v for k, v in metadonnees.items() if k != "content"}, "content": contenu})
    return morceaux


async def _get_collection_sample(
    client: OpenRAGClient, collection: str, max_files: int = 5
) -> list[dict]:
    """Get a sample of files from the collection to provide context.

    Used as fallback when semantic search returns no results
    (e.g. for vague questions like "de quoi parle cette collection ?").
    """
    try:
        files = await client.list_files(collection)
        if not files:
            return []

        # Take a sample: first, middle, and last files for variety
        sample_indices = set()
        n = len(files)
        # Always include first
        sample_indices.add(0)
        if n > 1:
            sample_indices.add(n - 1)
        if n > 2:
            sample_indices.add(n // 2)
        # Fill up to max_files
        for i in range(min(n, max_files)):
            sample_indices.add(i)

        sample = [files[i] for i in sorted(sample_indices) if i < n]
        return sample[:max_files]
    except Exception:
        return []


@router.post("/{collection}/generate-eval")
async def generate_eval_dataset(collection: str):
    """Auto-generate an evaluation dataset from the collection's content.

    Fetches sample chunks, sends them to the LLM, and asks it to produce
    Q&A pairs in the evaluation JSON format.
    """
    client = OpenRAGClient(timeout=120.0)

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="OpenRAG n'est pas accessible.",
        )

    # Get all files to understand the collection
    files = await client.list_files(collection)
    if not files:
        raise HTTPException(
            status_code=400,
            detail="La collection est vide. Indexez au moins un document.",
        )

    # Fetch content from a sample of files (best-effort). OpenRAG's per-file
    # content endpoint (get_file_content) is fragile and returns empty/errors on
    # a number of partitions, so we treat a successful read as a bonus, not a
    # requirement.
    sample_files = files[:15]  # max 15 chunks for context
    content_parts = []
    for f in sample_files:
        # fname et contenu proviennent de documents ingérés (non fiables) :
        # on les neutralise avant insertion dans le prompt (anti-injection).
        fname = sanitize_oneline(f.get("original_filename") or f.get("filename") or "?", max_len=200)
        try:
            file_id = f.get("file_id", "")
            text = await client.get_file_content(collection, file_id)
        except Exception:
            text = ""
        if text:
            content_parts.append(f"### {fname}\n{neutralize_for_prompt(text, max_len=800)}")

    model = f"openrag-{collection}"

    json_format = f"""{{
  "name": "{collection}-evaluation",
  "description": "Jeu de test genere automatiquement",
  "questions": [
    {{
      "id": "q1",
      "question": "La question ici ?",
      "expected_answer": "La reponse attendue basee sur le contenu.",
      "must_cite": ["mot-cle-1", "mot-cle-2"],
      "tags": ["theme"]
    }}
  ]
}}"""
    common_instructions = (
        "Produis exactement 8 questions-reponses variees qui couvrent les "
        "differents sujets du contenu.\n\n"
        "Reponds UNIQUEMENT avec un JSON valide, sans texte avant ou apres, "
        f"au format suivant :\n{json_format}"
    )

    # Quand on a pu lire des extraits, on ancre le LLM dessus. Sinon (endpoint de
    # contenu OpenRAG indisponible — cf. commit b2d714a), on se rabat sur le RAG
    # lui-même : OpenRAG auto-récupère depuis la partition, exactement comme
    # /chat. L'endpoint marche donc partout où le chat marche, au lieu de 400.
    if content_parts:
        context = wrap_untrusted("\n\n".join(content_parts), label="EXTRAITS")
        prompt = (
            f"Voici des extraits d'une collection de documents :\n\n{context}\n\n"
            "A partir de ces extraits, genere un jeu de test d'evaluation pour un "
            f"systeme RAG.\n{common_instructions}"
        )
    else:
        prompt = (
            "Tu as acces au contenu indexe de cette collection de documents via la "
            "recherche documentaire. En t'appuyant sur ce contenu reel, genere un jeu "
            f"de test d'evaluation pour un systeme RAG.\n{common_instructions}"
        )

    try:
        result = await client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=_CHAT_MAX_TOKENS,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur LLM: {e}")

    content = ""
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")

    # 1) Essai format riche JSON (expected_answer / must_cite quand le modèle s'y prête).
    dataset = None
    try:
        raw = content
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict) and parsed.get("questions"):
            dataset = parsed
    except (json.JSONDecodeError, IndexError, AttributeError):
        dataset = None

    # 2) Fallback robuste : les modèles RAG renvoient souvent du vide / du non-JSON
    #    sur un prompt JSON exigeant, mais produisent fiablement une liste de
    #    questions en texte (approche éprouvée par useBank).
    if not (dataset and dataset.get("questions")):
        questions = await _generate_questions_via_lines(client, model)
        if questions:
            dataset = {
                "name": f"{collection}-evaluation",
                "description": "Jeu de test genere automatiquement",
                "questions": questions,
            }

    if not (dataset and dataset.get("questions")):
        return {
            "name": f"{collection}-evaluation",
            "description": "Jeu de test genere automatiquement",
            "questions": [],
            "raw_response": content,
            "error": "Le LLM n'a pas pu generer de questions. Reessayez.",
        }

    # Add out-of-scope questions to test RAG robustness
    dataset.setdefault("questions", []).extend(_OUT_OF_SCOPE)
    return dataset


# Le pied « Sources : 1. [fichier](url) … » qu'OpenRAG ajoute à la réponse : les
# mêmes fichiers que `sources`, en noms bruts. Les puces les portent déjà, lisibles.
_PIED_SOURCES_RE = re.compile(
    r"\n+(?:-{3,}[ \t]*\n+)?\**[ \t]*Sources?[ \t]*:?[ \t]*\**[ \t]*\n+"
    r"(?:[ \t]*(?:\d+[.)]|[-*])[ \t]*\[[^\]]*\]\([^)]*\)[ \t]*\n?)+[ \t]*$",
    re.IGNORECASE,
)


def retirer_le_pied_sources(texte: str) -> str:
    """Retire la liste « Sources : » en fin de réponse — elle doublonne les puces."""
    if not texte:
        return texte
    return _PIED_SOURCES_RE.sub("", texte).rstrip()


def situer_source(s: dict) -> dict:
    """Un libellé lisible pour une source : le titre de sa section (qui porte le
    département, le code, l'année…), à défaut celui du document, à défaut rien —
    le front retombe alors sur le nom de fichier. Les morceaux des amorces
    commencent par `# <document>` puis `## <section>` (ingestion.situer).

    ⚠ Le morceau rendu par /search porte d'abord le résumé qu'OpenRAG lui ajoute
    (`[CONTEXT] … [CHUNK_START]`) : les titres arrivent APRÈS. On lit donc au-delà,
    et on s'arrête au premier titre de chaque niveau."""
    titre_doc = titre_section = ""
    for ligne in (s.get("content") or "").splitlines()[:40]:
        if ligne.startswith("## ") and not titre_section:
            titre_section = ligne[3:].strip()
        elif ligne.startswith("# ") and not titre_doc:
            titre_doc = ligne[2:].strip()
        if titre_doc and titre_section:
            break
    if titre_doc:
        s["titre_document"] = titre_doc
    if titre_section:
        s["titre_section"] = titre_section
    libelle = titre_section or titre_doc
    if libelle:
        s["libelle"] = libelle
    return s


_LIEN_OPENRAG_RE = re.compile(r"https?://[^\s)\]\"']+/(?:static|extract)/(\d+)")


def relier_au_proxy(texte: str) -> str:
    """Un lien OpenRAG (`…/static/<id>` ou `…/extract/<id>`) devient un lien de
    même origine vers notre proxy : `/api/openrag/extract/<id>`. Le morceau et le
    document portent le même identifiant chez OpenRAG ; `/static` exige une
    session de son SSO que le navigateur n'a pas, `/extract` accepte le jeton."""
    if not texte:
        return texte
    return _LIEN_OPENRAG_RE.sub(lambda m: f"/api/openrag/extract/{m.group(1)}", texte)


@router.post("/{collection}/chat")
async def playground_chat(collection: str, req: PlaygroundChatRequest,
                          user: CurrentUser = Depends(current_user)):
    """Quick RAG chat test against a collection.

    If OpenRAG RAG returns no sources, falls back to manual context injection.
    """
    # La mesure d'usage : une ligne par question (sans son texte). Ne bloque jamais.
    await accueil.noter_question(collection, user.sub)
    client = OpenRAGClient(timeout=120.0)

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="OpenRAG n'est pas accessible. Verifiez que le service est demarre.",
        )

    # Load collection system prompt if not overridden
    system_prompt = req.system_prompt
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
    messages.append({"role": "user", "content": req.question})

    try:
        result = await client.chat(
            model=model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=_CHAT_MAX_TOKENS,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur OpenRAG: {e}")

    # Extract response and sources
    content = ""
    sources = []
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")

    extra_str = result.get("extra", "")
    if extra_str:
        try:
            extra = json.loads(extra_str) if isinstance(extra_str, str) else extra_str
            sources = extra.get("sources", [])
        except (json.JSONDecodeError, AttributeError):
            pass

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
        morceaux = await _morceaux_par_recherche(client, collection, req.question)
        if morceaux:
            fallback_used = repli_recherche = True
            sources = morceaux
            extraits = wrap_untrusted(
                "\n\n---\n\n".join(
                    neutralize_for_prompt(m.get("content") or "", max_len=_EXTRAIT_MAX_CARS)
                    for m in morceaux
                ),
                label="DOCUMENTS",
            )
            messages_repli = [
                {"role": "system", "content": (system_prompt + "\n\n" if system_prompt else "") + (
                    "Réponds à la question en te fondant UNIQUEMENT sur les documents fournis ci-dessous. "
                    "Si la réponse ne s'y trouve pas, dis-le simplement."
                )},
                {"role": "user", "content": f"{extraits}\n\n{req.question}"},
            ]
            try:
                resultat_repli = await client.chat(
                    model=model, messages=messages_repli,
                    temperature=req.temperature, max_tokens=_CHAT_MAX_TOKENS,
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

            fallback_system = (
                system_prompt + "\n\n" if system_prompt else ""
            ) + (
                f"Cette collection '{collection}' contient {total_files_count} documents indexes. "
                "Reponds a la question en te basant sur les noms de fichiers (fournis comme donnee) "
                "pour decrire le contenu de la collection."
            )

            fallback_messages = [
                {"role": "system", "content": fallback_system},
                {"role": "user", "content": f"{files_block}\n\n{req.question}"},
            ]

            try:
                fallback_result = await client.chat(
                    model=model,
                    messages=fallback_messages,
                    temperature=req.temperature,
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

    # Règle 3 : une collection non publiée à tous répond avec la mention.
    mention = None
    try:
        from app.services.collectif_store import fiche
        from app.services.etats import mention_verification
        mention = mention_verification((await fiche(collection))["etat_collab"])
    except Exception:  # noqa: BLE001 — fiche absente : pas de mention, pas de panne
        mention = None
    if mention:
        content = f"⚠ {mention}\n\n{content}"

    return {
        "response": content,
        "mention": mention,
        "sources": sources,
        "source_names": source_names,
        "model": model,
        "system_prompt_used": bool(system_prompt),
        "fallback_used": fallback_used,
        "repli_recherche": repli_recherche,
    }
