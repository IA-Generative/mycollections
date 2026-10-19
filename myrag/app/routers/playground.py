"""Playground router — quick RAG test for a collection."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser, current_user
from app.services import accueil, liens
from app.services.openrag_client import FichierOpenRAG, OpenRAGClient
from app.services.reponse import ErreurReponse, repondre

router = APIRouter(prefix="/api/playground", tags=["Playground"])

# Les modèles RAG d'OpenRAG sont des modèles « à raisonnement » : ils émettent
# d'abord un reasoning_content (chaîne de pensée), puis la réponse dans content.
# Avec la limite par défaut (~1024 tokens), le raisonnement épuise le budget et
# content ressort VIDE (finish_reason=length) -> réponses vides côté playground
# et faux KO à l'évaluation. On donne donc une marge confortable.
_CHAT_MAX_TOKENS = 4096


class PlaygroundChatRequest(BaseModel):
    question: str
    system_prompt: str = ""
    top_k: int = 5
    temperature: float = 0.1


#: Ce qu'on garde d'un morceau injecté en contexte : de quoi répondre sans noyer
#: le modèle ni faire exploser la fenêtre quand cinq morceaux arrivent ensemble.
_EXTRAIT_MAX_CARS = 2000


async def _morceaux_par_recherche(client: OpenRAGClient, collection: str, question: str, top_k: int = 5) -> list[dict]:
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
    for d in resultat.documents:
        metadonnees = d.metadata or {}
        contenu = d.content or metadonnees.get("content") or ""
        if not contenu:
            continue
        morceaux.append({**{k: v for k, v in metadonnees.items() if k != "content"}, "content": contenu})
    return morceaux


async def _get_collection_sample(client: OpenRAGClient, collection: str, max_files: int = 5) -> list[FichierOpenRAG]:
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


def _lien_extrait(ident: str) -> str:
    """Le lien de même origine vers notre proxy, signé : il s'ouvre dans un onglet neuf,
    sans jeton (app/services/liens.py)."""
    return liens.signer(f"/api/openrag/extract/{ident}", liens.portee_extrait(ident))


def relier_au_proxy(texte: str) -> str:
    """Un lien OpenRAG (`…/static/<id>` ou `…/extract/<id>`) devient un lien de
    même origine vers notre proxy : `/api/openrag/extract/<id>`, signé. Le morceau et le
    document portent le même identifiant chez OpenRAG ; `/static` exige une
    session de son SSO que le navigateur n'a pas, `/extract` accepte le jeton."""
    if not texte:
        return texte
    return _LIEN_OPENRAG_RE.sub(lambda m: _lien_extrait(m.group(1)), texte)


_URL_OPENRAG_RE = re.compile(r"/(extract|file|static)/([^?#\s]+)")


def signer_les_liens_de_la_source(s: dict) -> dict:
    """`chunk_url` et `file_url` d'une source visent l'API d'OpenRAG : on les ramène sur notre
    proxy, avec une signature, pour que les puces s'ouvrent sans jeton dans un onglet.

    Un morceau rendu par le repli (/search) n'a pas de `chunk_url`, seulement son `_id` : sans
    lien, sa puce n'offrait pas « Lire l'extrait ». On le construit depuis l'identifiant."""
    ident_morceau = s.get("_id") or s.get("chunk_id")
    if not s.get("chunk_url") and ident_morceau and str(ident_morceau).isdigit():
        s["chunk_url"] = _lien_extrait(str(ident_morceau))
    for cle in ("chunk_url", "file_url"):
        url = s.get(cle)
        if not isinstance(url, str) or not url:
            continue
        m = _URL_OPENRAG_RE.search(url)
        if not m or "/api/openrag/" in url:
            continue
        genre, ident = m.group(1), m.group(2)
        s[cle] = liens.signer(f"/api/openrag/{genre}/{ident}", liens.portee_extrait(ident))
    return s


@router.post("/{collection}/chat")
async def playground_chat(collection: str, req: PlaygroundChatRequest, user: CurrentUser = Depends(current_user)):
    """Quick RAG chat test against a collection.

    If OpenRAG RAG returns no sources, falls back to manual context injection.
    """
    # Poser une question à une collection demande de pouvoir la lire : la réponse cite ses
    # sources et en remet des liens signés (diagnostic d'octobre 2026, P0).
    from app.routers.publication import _fiche_pour

    await _fiche_pour(collection, user, ecrire=False)
    # La mesure d'usage : une ligne par question (sans son texte). Ne bloque jamais.
    await accueil.noter_question(collection, user.sub)
    client = OpenRAGClient(timeout=120.0)

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="OpenRAG n'est pas accessible. Verifiez que le service est demarre.",
        )

    try:
        rep = await repondre(collection, req.question, client=client, system_prompt=req.system_prompt, temperature=req.temperature)
    except ErreurReponse as e:
        raise HTTPException(status_code=502, detail=str(e))
    content = f"⚠ {rep.mention}\n\n{rep.contenu}" if rep.mention else rep.contenu
    return {
        "response": content,
        "mention": rep.mention,
        "sources": rep.sources,
        "source_names": rep.source_names,
        "model": rep.modele,
        "system_prompt_used": rep.system_prompt_used,
        "fallback_used": rep.fallback_used,
        "repli_recherche": rep.repli == "recherche",
    }


# ─── Étape 4 de l'assistant de création : le test technique ──────────────────────────────────

#: Trois questions suffisent à voir si la collection répond ; au-delà, c'est la page Qualité.
NB_SUGGESTIONS = 3
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_SEPARATEURS = re.compile(r"[-_]+")


def titre_lisible(titre: str) -> str:
    """« circulaire-peines_2026.pdf » → « circulaire peines 2026 » : un nom de fichier qui se lit."""
    t = _SEPARATEURS.sub(" ", _EXTENSION.sub("", (titre or "").strip())).strip()
    return " ".join(t.split())


def questions_depuis_documents(titres: list[str], n: int = NB_SUGGESTIONS) -> list[str]:
    """Des questions qui ne supposent rien du contenu : une par document, d'après son titre."""
    vues: set[str] = set()
    questions: list[str] = []
    for brut in titres:
        t = titre_lisible(brut)
        if len(t) < 3 or t.lower() in vues:
            continue
        vues.add(t.lower())
        questions.append(f"Que dit le document « {t[:100]} » ?")
        if len(questions) >= n:
            break
    return questions


_INTERTITRE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_EMPHASE = re.compile(r"[*_`]+")


def questions_depuis_intertitres(contenus: list[str], n: int = NB_SUGGESTIONS) -> list[str]:
    """Une question par intertitre de passage (« ## Code de contrôle ») : le texte lui-même dit de
    quoi il parle, mieux qu'un nom de fichier fabriqué par le découpage."""
    vus: set[str] = set()
    questions: list[str] = []
    for contenu in contenus:
        m = _INTERTITRE.search(contenu or "")
        if not m:
            continue
        intertitre = " ".join(_EMPHASE.sub("", m.group(1)).split()).strip(" :.-")
        if not 3 <= len(intertitre) <= 100 or intertitre.lower() in vus:
            continue
        vus.add(intertitre.lower())
        questions.append(f"Que dit le texte sur « {intertitre} » ?")
        if len(questions) >= n:
            break
    return questions


async def _questions_du_jeu(collection: str, n: int) -> list[str]:
    """Les questions du jeu de la collection — jamais celles d'un usager (origine « avis »)."""
    from sqlalchemy import select

    from app.database import async_session
    from app.models.db import PaireQA

    async with async_session() as session:
        lignes = (
            (
                await session.execute(
                    select(PaireQA.question)
                    .where(
                        PaireQA.collection_name == collection,
                        PaireQA.origine != "avis",
                        PaireQA.hors_sujet.is_(False),
                        PaireQA.relecture != "rejete",
                    )
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    propres = [q.strip() for q in lignes if q and 3 <= len(q.strip()) <= 160]
    return list(dict.fromkeys(propres))[:n]


@router.get("/{collection}/suggestions")
async def suggestions(collection: str, user: CurrentUser = Depends(current_user)):
    """Trois questions pour le test technique de l'étape 4 : d'abord celles du jeu de la collection
    (hors questions d'usagers), puis une par intertitre de passage, puis une par document d'après
    son titre. Lecture requise.
    OpenRAG injoignable : on rend ce qu'on a, la personne tape sa question."""
    from app.routers.publication import _fiche_pour
    from app.services import corpus

    await _fiche_pour(collection, user, ecrire=False)
    questions = await _questions_du_jeu(collection, NB_SUGGESTIONS)
    origine = "jeu" if questions else "documents"

    def completer(autres: list[str]) -> None:
        for q in autres:
            if len(questions) >= NB_SUGGESTIONS:
                return
            if q not in questions:
                questions.append(q)

    client = OpenRAGClient(timeout=10.0)
    if len(questions) < NB_SUGGESTIONS:
        try:
            morceaux = await client.partition_chunks(collection, limit=50) or []
        except Exception:  # noqa: BLE001 — sans passages, on passe aux titres
            morceaux = []
        completer(questions_depuis_intertitres([m.content for m in morceaux]))
    if len(questions) < NB_SUGGESTIONS:
        try:
            fichiers = await client.list_files(collection)
        except Exception:  # noqa: BLE001 — sans liste de documents, pas de suggestion de plus
            fichiers = []
        completer(questions_depuis_documents([corpus.resumer_fichier(f)["titre"] for f in fichiers]))
    return {"questions": questions, "origine": origine if questions else None}
