"""Recherche pour Mon portail — le contrat de recherche MirAI (version 1).

Mon portail, un site statique servi sur une autre origine, interroge Mes collections depuis le
navigateur avec le jeton de la personne (realm du SSO, client `mysearch`) :

- `GET /api/v1/search/scopes` : les collections que la personne peut lire, à cocher ;
- `GET /api/v1/search?q=&limit=&scope=&from=&to=` : les passages qui répondent, groupés par
  document, au plus trois par document.

Recherche SEULEMENT : aucun modèle de langage derrière ces routes (jamais
`/v1/chat/completions`), `q` est un texte à chercher, pas une consigne. Les droits sont ceux
du reste de l'application (`access.can_read`) ; une collection demandée sans droit, ou
inconnue, est IGNORÉE, pas refusée. Les liens rendus s'ouvrent sans jeton : ils sont signés
côté serveur, après le contrôle des droits (`app/services/liens.py`). Le contenu est rendu en
texte brut, borné, jamais en HTML.

Les erreurs suivent le contrat : `{"error": {"code", "message"}}`, et toutes les réponses
portent `Cache-Control: no-store`. Ni `q` ni les contenus ne sont journalisés.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from starlette.datastructures import Headers, MutableHeaders

from app.auth import CurrentUser, _bearer_scheme, _exiger_le_groupe, audience_acceptee, current_user, decoder_le_jeton
from app.config import settings
from app.services import access, liens
from app.services.collection_store import list_collections
from app.services.morceau import decouper_morceau
from app.services.nommage import titre_de
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.recherche")

PREFIXE = "/api/v1/search"
SOURCE = "mycollections"
Q_MAX = 1000
LIMITE_DEFAUT = 20
LIMITE_MAX = 50
PASSAGES_MAX = 3
TAILLE_EXTRAIT = 300


# ─── Erreurs du contrat ──────────────────────────────────────────────────────────────────────

class ErreurRecherche(Exception):
    def __init__(self, statut: int, code: str, message: str, entetes: dict[str, str] | None = None):
        super().__init__(code)
        self.statut, self.code, self.message, self.entetes = statut, code, message, entetes or {}


def _erreur(statut: int, code: str, message: str, entetes: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=statut, content={"error": {"code": code, "message": message}},
                        headers={**(entetes or {}), "Cache-Control": "no-store"})


_CODES_HTTP = {
    401: ("invalid_token", "Jeton absent, expiré ou invalide"),
    403: ("forbidden", "Accès refusé"),
    404: ("not_found", "Introuvable"),
    429: ("rate_limited", "Trop de recherches, réessayez dans un instant"),
    503: ("search_unavailable", "Recherche momentanément indisponible"),
}


class _RouteRecherche(APIRoute):
    """Chaque réponse d'une route du contrat : erreurs au format du contrat, `no-store`.

    Les exceptions des dépendances (garde du jeton, identité) passent aussi par ici : elles
    sont résolues dans le gestionnaire de la route."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def gestionnaire(request: Request) -> Response:
            try:
                reponse = await original(request)
            except ErreurRecherche as e:
                return _erreur(e.statut, e.code, e.message, e.entetes)
            except RequestValidationError:
                return _erreur(400, "invalid_query", "Paramètres de recherche invalides")
            except HTTPException as e:
                code, message = _CODES_HTTP.get(e.status_code, ("error", "Erreur"))
                return _erreur(e.status_code, code, message, dict(e.headers or {}))
            reponse.headers["Cache-Control"] = "no-store"
            return reponse

        return gestionnaire


# ─── Garde : jeton, audience, groupe exigé, débit ────────────────────────────────────────────

def _garde(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> None:
    """Le jeton est valide, nous est destiné, et son porteur passe la garde de groupe.

    Synchrone : FastAPI la joue dans un fil à part (le JWKS se lit en bloquant, en cache).
    Ensuite `current_user` relit le jeton (clés en cache) pour en tirer l'identité."""
    if not settings.auth_enabled:
        return
    if credentials is None or not credentials.credentials:
        raise ErreurRecherche(401, "invalid_token", "Jeton absent")
    try:
        claims = decoder_le_jeton(credentials.credentials)
    except HTTPException as e:
        if e.status_code == 503:
            raise ErreurRecherche(503, "search_unavailable", "Service d'authentification indisponible")
        raise ErreurRecherche(401, "invalid_token", "Jeton expiré ou invalide")
    if not audience_acceptee(claims):
        # Le client émetteur suffit au diagnostic ; rien qui nomme la personne.
        logger.warning("Recherche refusée : audience non acceptée (azp=%s)", str(claims.get("azp", ""))[:64])
        raise ErreurRecherche(403, "audience_mismatch", "Ce jeton n'est pas destiné à Mes collections")
    try:
        _exiger_le_groupe(claims)
    except HTTPException:
        raise ErreurRecherche(403, "forbidden", "Accès réservé aux membres du groupe autorisé")


#: Recherches comptées par personne et par minute (mémoire du processus : une limite par pod).
_fenetres: dict[str, tuple[int, int]] = {}


def _limiter(cle: str) -> None:
    plafond = settings.recherche_par_minute
    if plafond <= 0:
        return
    maintenant = time.time()
    minute = int(maintenant // 60)
    vue, compte = _fenetres.get(cle, (minute, 0))
    compte = compte + 1 if vue == minute else 1
    if len(_fenetres) > 10000:
        for k in [k for k, (m, _) in _fenetres.items() if m != minute]:
            del _fenetres[k]
    _fenetres[cle] = (minute, compte)
    if compte > plafond:
        raise ErreurRecherche(429, "rate_limited", "Trop de recherches, réessayez dans un instant",
                              {"Retry-After": str(60 - int(maintenant) % 60)})


async def _utilisateur(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """L'identité de l'appelant, qui DOIT porter un `sub` (jeton, ou /userinfo à défaut) :
    sans lui, ni « owner » ni le compte des recherches ne se rapportent à une personne."""
    if not user.sub:
        raise ErreurRecherche(401, "invalid_token", "Jeton sans identité (sub)")
    return user


router = APIRouter(prefix=PREFIXE, tags=["recherche"], route_class=_RouteRecherche,
                   dependencies=[Depends(_garde)])


# ─── Droits : ce que la personne lit, et à quel titre ────────────────────────────────────────

def _droit(fiche: dict, user: CurrentUser) -> tuple[str, str]:
    """(right, group) : `owner/mine` pour le créateur, `public/public` pour une collection
    ouverte à tous, `reader/shared` sinon (groupe, administration, superadmin)."""
    cree_par = fiche.get("created_by")
    if cree_par and user.sub and cree_par == user.sub:
        return "owner", "mine"
    if fiche.get("scope") == "public":
        return "public", "public"
    return "reader", "shared"


async def _collections_lisibles(user: CurrentUser) -> list[dict]:
    """Les fiches (hors archivées) que la personne peut lire — la règle de `access.can_read`,
    celle de la liste des collections. Une partition sans fiche n'est pas proposée."""
    fiches = await list_collections(include_archived=False)
    return [f for f in fiches if access.can_read(
        name=f["name"], scope=f.get("scope"), scope_groups=f.get("scope_groups"),
        created_by=f.get("created_by"), user_groups=user.groups, user_sub=user.sub)]


_ORDRE_GROUPES = {"mine": 0, "shared": 1, "public": 2}


@router.get("/scopes")
async def perimetres(user: CurrentUser = Depends(_utilisateur)):
    """Les collections à cocher. Légère : la base seule, aucun appel au moteur."""
    scopes = []
    for f in await _collections_lisibles(user):
        right, group = _droit(f, user)
        scopes.append({"id": f["name"], "title": titre_de(f), "group": group, "right": right})
    scopes.sort(key=lambda s: (_ORDRE_GROUPES[s["group"]], s["title"].casefold()))
    return {"scopes": scopes}


# ─── Paramètres ──────────────────────────────────────────────────────────────────────────────

def _invalide(message: str) -> ErreurRecherche:
    return ErreurRecherche(400, "invalid_query", message)


def _lire_limite(brut: str | None) -> int:
    if brut is None or brut == "":
        return LIMITE_DEFAUT
    try:
        limite = int(brut)
    except ValueError:
        raise _invalide("limit doit être un entier")
    if not 1 <= limite <= LIMITE_MAX:
        raise _invalide(f"limit doit être entre 1 et {LIMITE_MAX}")
    return limite


_DATE_SEULE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _lire_borne(brut: str | None, nom: str) -> date | datetime | None:
    """`AAAA-MM-JJ` → une date (comparée au jour du résultat) ; sinon un datetime ISO 8601."""
    if brut is None or not brut.strip():
        return None
    v = brut.strip()
    try:
        if _DATE_SEULE.match(v):
            return date.fromisoformat(v)
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise _invalide(f"{nom} : date illisible")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _dans_les_bornes(quand: datetime | None, depuis, jusqu: Any) -> bool:
    if depuis is None and jusqu is None:
        return True
    if quand is None:
        return False
    for borne, sens in ((depuis, 1), (jusqu, -1)):
        if borne is None:
            continue
        valeur = quand.date() if not isinstance(borne, datetime) else quand
        if (valeur < borne) if sens == 1 else (valeur > borne):
            return False
    return True


def _lire_perimetre(request: Request) -> list[str] | None:
    """`scope=a,b` (ou répété) → les noms demandés, dans l'ordre ; None si absent."""
    valeurs = request.query_params.getlist("scope")
    if not valeurs:
        return None
    noms: list[str] = []
    for v in valeurs:
        for n in v.split(","):
            n = n.strip()
            if n and n not in noms:
                noms.append(n)
    return noms


# ─── Texte : brut, borné, surligné en unités UTF-16 ──────────────────────────────────────────

def _texte_brut(texte: str) -> str:
    """Un passage tel qu'on peut l'afficher : sans balises OpenRAG, sans HTML, sans
    caractères de contrôle, sans le gros du balisage Markdown, espaces resserrés."""
    _, _, corps = decouper_morceau(texte)
    corps = re.sub(r"<[^>]*>", " ", corps)
    corps = html.unescape(corps)
    corps = re.sub(r"<[^>]*>", " ", corps)  # `&lt;b&gt;` décodé redevient une balise
    corps = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", corps)
    corps = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", corps)
    corps = re.sub(r"(\*\*|__|`+)", "", corps)
    corps = re.sub(r"(^|\s)#{1,6}\s", " ", corps)
    corps = "".join(c if c in "\n\t" or unicodedata.category(c)[0] != "C" else " " for c in corps)
    return re.sub(r"\s+", " ", corps).strip()


_VARIANTES = {"a": "aàâä", "e": "eéèêë", "i": "iîï", "o": "oôö", "u": "uùûü", "c": "cç", "y": "yÿ", "n": "nñ"}


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def _motif(q: str) -> re.Pattern | None:
    """Les mots de la question (3 lettres et plus, ou des chiffres), cherchés sans égard
    à la casse ni aux accents, en début de mot."""
    termes: list[str] = []
    for mot in re.findall(r"\w+", _sans_accents(q).lower()):
        if (len(mot) >= 3 or mot.isdigit()) and mot not in termes:
            termes.append(mot)
    if not termes:
        return None
    termes.sort(key=len, reverse=True)
    morceaux = ["".join(f"[{_VARIANTES[c]}]" if c in _VARIANTES else re.escape(c) for c in t)
                for t in termes[:20]]
    return re.compile(r"(?<!\w)(?:" + "|".join(morceaux) + ")", re.IGNORECASE)


def _u16(s: str, i: int) -> int:
    """Position `i` (en caractères Python) exprimée en unités UTF-16, comme `String.length`."""
    return len(s[:i].encode("utf-16-le")) // 2


def _surlignages(extrait: str, motif: re.Pattern | None) -> list[list[int]]:
    if motif is None:
        return []
    return [[_u16(extrait, m.start()), _u16(extrait, m.end())] for m in motif.finditer(extrait)]


def _extrait(texte: str, motif: re.Pattern | None) -> str:
    """Environ 300 caractères autour de la première occurrence (le début, à défaut)."""
    if len(texte) <= TAILLE_EXTRAIT:
        return texte
    m = motif.search(texte) if motif else None
    debut = max(0, m.start() - 80) if m else 0
    if debut:
        espace = texte.find(" ", debut, debut + 20)
        debut = espace + 1 if espace >= 0 else debut
    fin = min(len(texte), debut + TAILLE_EXTRAIT - 4)
    if fin < len(texte):
        espace = texte.rfind(" ", debut + TAILLE_EXTRAIT // 2, fin)
        fin = espace if espace > 0 else fin
    return ("… " if debut else "") + texte[debut:fin].strip() + (" …" if fin < len(texte) else "")


# ─── Moteur : un appel pour toutes les collections, sinon une par une ────────────────────────

class _MoteurIndisponible(Exception):
    pass


async def _interroger(partitions: list[str], q: str, top_k: int) -> list[dict]:
    """Les morceaux qu'OpenRAG rend pour ces partitions (jamais une liste vide : OpenRAG la
    lirait comme « toutes »). Un seul appel ; s'il est refusé (une partition absente du
    moteur, par exemple), un appel par partition, en parallèle, les refus écartés."""
    delai = settings.recherche_delai_s
    client = OpenRAGClient(timeout=delai)

    async def un_appel(cibles: list[str]) -> list[dict]:
        rendu = await asyncio.wait_for(client.search(cibles, q, top_k=top_k), timeout=delai)
        docs = (rendu or {}).get("documents") if isinstance(rendu, dict) else None
        return [d for d in docs or [] if isinstance(d, dict)]

    try:
        return await un_appel(partitions)
    except httpx.HTTPStatusError as e:
        if e.response.status_code >= 500:
            raise _MoteurIndisponible from e
        if len(partitions) == 1:
            return []
    except (httpx.HTTPError, asyncio.TimeoutError, OSError) as e:
        raise _MoteurIndisponible from e

    rendus = await asyncio.gather(*(un_appel([p]) for p in partitions), return_exceptions=True)
    reussis = [r for r in rendus if not isinstance(r, BaseException)]
    pannes = [r for r in rendus if isinstance(r, BaseException)
              and not (isinstance(r, httpx.HTTPStatusError) and r.response.status_code < 500)]
    if not reussis and pannes:
        raise _MoteurIndisponible
    # Entrelacés rang par rang : aucune collection ne passe devant les autres d'office.
    fusion: list[dict] = []
    for rang in range(max((len(r) for r in reussis), default=0)):
        fusion.extend(r[rang] for r in reussis if rang < len(r))
    return fusion


# ─── Résultats ───────────────────────────────────────────────────────────────────────────────

_CLES_SCORE = ("relevance_score", "rerank_score", "combined_score", "score")
_CLES_DATE = ("created_at", "modified_at", "date", "indexed_at")
_ID_LIEN = re.compile(r"/extract/([^/?#\s]+)")


def _score(meta: dict) -> float | None:
    for cle in _CLES_SCORE:
        v = meta.get(cle)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return round(float(v), 4)
    return None


def _date(meta: dict) -> datetime | None:
    for cle in _CLES_DATE:
        v = meta.get(cle)
        try:
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                return datetime.fromtimestamp(v, tz=timezone.utc)
            if isinstance(v, str) and v.strip():
                dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, OverflowError, OSError):
            continue
    return None


def _ident_morceau(doc: dict, meta: dict) -> str | None:
    ident = meta.get("_id")
    if ident is None:
        m = _ID_LIEN.search(str(doc.get("link") or ""))
        ident = m.group(1) if m else None
    ident = str(ident) if ident is not None else ""
    return ident if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ident) else None


def _origine_publique() -> str:
    return (settings.recherche_url_publique or settings.myrag_public_url).rstrip("/")


def _lien(ident: str | None) -> str | None:
    """Le lien de lecture du morceau, signé (12 h), absolu. Appelé seulement pour un morceau
    d'une collection dont le droit de lecture vient d'être vérifié."""
    if not ident:
        return None
    return _origine_publique() + liens.signer(f"/api/openrag/extract/{ident}", liens.portee_extrait(ident))


def _titre_du_document(meta: dict, fichier: str) -> str:
    titre = meta.get("title") if isinstance(meta.get("title"), str) else ""
    nom = titre or (meta.get("filename") if isinstance(meta.get("filename"), str) else "") or fichier
    nom = re.sub(r"\.(md|txt|markdown)$", "", (nom or "").strip(), flags=re.I)
    return _texte_brut(nom)[:200]


def _page(meta: dict) -> int | None:
    p = meta.get("page")
    return p if isinstance(p, int) and not isinstance(p, bool) and p > 0 else None


def _construire(docs: list[dict], fiches: dict[str, dict], user: CurrentUser,
                motif: re.Pattern | None, depuis, jusqu) -> list[dict]:
    """Les morceaux groupés par document (rang d'OpenRAG conservé), au plus trois passages."""
    resultats: dict[tuple[str, str], dict] = {}
    for doc in docs:
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        partition = meta.get("partition")
        fiche = fiches.get(partition) if isinstance(partition, str) else None
        if fiche is None:
            continue  # hors des collections lisibles demandées : jamais rendu, jamais signé
        ident = _ident_morceau(doc, meta)
        brut = doc.get("content") if isinstance(doc.get("content"), str) else ""
        _, fichier, _ = decouper_morceau(brut)
        texte = _texte_brut(brut)
        if not texte:
            continue
        cle = (partition, str(meta.get("file_id") or ident or fichier))
        r = resultats.get(cle)
        if r is None:
            quand = _date(meta)
            right, _ = _droit(fiche, user)
            titre = _titre_du_document(meta, fichier) or titre_de(fiche)
            r = resultats[cle] = {
                "id": f"{partition}:{cle[1]}",
                "title": titre,
                "date": quand.isoformat() if quand else None,
                "url": _lien(ident),
                "score": _score(meta),
                "hits": [],
                "context": {"collection": {"id": partition, "title": titre_de(fiche)}, "right": right},
                "_quand": quand,
            }
        if len(r["hits"]) >= PASSAGES_MAX:
            continue
        s = _score(meta)
        if s is not None and (r["score"] is None or s > r["score"]):
            r["score"] = s
        extrait = _extrait(texte, motif)
        r["hits"].append({
            "snippet": extrait,
            "highlights": _surlignages(extrait, motif),
            "field": "content",
            "location": {"start_seconds": None, "end_seconds": None, "page": _page(meta)},
            "speaker": None,
            "url": _lien(ident) or r["url"],
        })
    sortie = []
    for r in resultats.values():
        if not _dans_les_bornes(r.pop("_quand"), depuis, jusqu):
            continue
        if not r["url"]:
            r["url"] = next((h["url"] for h in r["hits"] if h["url"]), None)
        sortie.append(r)
    return sortie


@router.get("")
async def rechercher(request: Request, q: str | None = None, limit: str | None = None,
                     user: CurrentUser = Depends(_utilisateur)):
    """Les documents des collections lisibles qui répondent à `q`."""
    _limiter(user.sub)
    texte = (q or "").strip()
    if not texte:
        raise _invalide("q est obligatoire")
    if len(texte) > Q_MAX:
        raise _invalide(f"q dépasse {Q_MAX} caractères")
    limite = _lire_limite(limit)
    depuis = _lire_borne(request.query_params.get("from"), "from")
    jusqu = _lire_borne(request.query_params.get("to"), "to")
    demandees = _lire_perimetre(request)

    lisibles = {f["name"]: f for f in await _collections_lisibles(user)}
    # Une collection inconnue ou sans droit est ignorée, pas refusée (contrat).
    noms = [n for n in demandees if n in lisibles] if demandees is not None else list(lisibles)
    vide = {"source": SOURCE, "query": texte, "total": 0, "truncated": False, "results": []}
    if not noms:
        return vide

    debut = time.monotonic()
    top_k = min(200, max(20, limite * 3))
    try:
        docs = await _interroger(noms, texte, top_k)
    except _MoteurIndisponible:
        logger.warning("Recherche : moteur indisponible (%d collection(s))", len(noms))
        raise ErreurRecherche(503, "search_unavailable", "Recherche momentanément indisponible")

    resultats = _construire(docs, {n: lisibles[n] for n in noms}, user, _motif(texte), depuis, jusqu)
    # Journal sans la question ni les contenus : des tailles et une durée.
    logger.info("Recherche : %d collection(s), %d morceau(x), %d résultat(s), %d ms",
                len(noms), len(docs), len(resultats), int((time.monotonic() - debut) * 1000))
    return {"source": SOURCE, "query": texte, "total": len(resultats),
            "truncated": len(resultats) > limite, "results": resultats[:limite]}


# ─── CORS des seules routes du contrat ───────────────────────────────────────────────────────

def _route_du_contrat(chemin: str) -> bool:
    chemin = chemin.rstrip("/")
    return chemin.endswith(PREFIXE) or chemin.endswith(PREFIXE + "/scopes")


class CorsRecherche:
    """CORS des routes du contrat, distinct du CORS global de l'application.

    Origines lues dans `MYCOLLECTIONS_RECHERCHE_ORIGINES` ; `GET` seulement, en-tête
    `Authorization` seulement, sans `Allow-Credentials` ; `Vary: Origin` et `no-store` sur
    tout ce qui sort. À poser APRÈS le CORS global (il l'enveloppe) : l'origine est retirée de
    la requête transmise, le CORS global ne s'en mêle pas."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _route_du_contrat(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        entetes = Headers(scope=scope)
        origine = entetes.get("origin")
        permises = {o.strip().rstrip("/") for o in settings.recherche_origines.split(",") if o.strip()}
        permise = origine if origine and origine.rstrip("/") in permises else None

        if scope["method"] == "OPTIONS" and origine and "access-control-request-method" in entetes:
            demandes = {h.strip().lower() for h in entetes.get("access-control-request-headers", "").split(",") if h.strip()}
            if permise and entetes["access-control-request-method"].upper() == "GET" and demandes <= {"authorization"}:
                reponse: Response = Response(status_code=204, headers={
                    "Access-Control-Allow-Origin": permise,
                    "Access-Control-Allow-Methods": "GET",
                    "Access-Control-Allow-Headers": "Authorization",
                    "Access-Control-Max-Age": "600",
                    "Vary": "Origin",
                    "Cache-Control": "no-store",
                })
            else:
                reponse = PlainTextResponse("Origine ou requête non autorisée", status_code=403,
                                            headers={"Vary": "Origin", "Cache-Control": "no-store"})
            await reponse(scope, receive, send)
            return

        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"origin"]

        async def envoyer(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h["Cache-Control"] = "no-store"
                h.add_vary_header("Origin")
                if permise:
                    h["Access-Control-Allow-Origin"] = permise
                    h["Access-Control-Expose-Headers"] = "Retry-After"
            await send(message)

        await self.app(scope, receive, envoyer)
