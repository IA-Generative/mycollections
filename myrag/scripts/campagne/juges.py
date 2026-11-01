"""Les juges de la campagne : déterministes d'abord, un juge-modèle en option.

Déterministes (aucun appel) :
- consigne retenue à raison ou à tort (le plan dit `consigne`) ;
- sources contactées (les étapes du plan), relais exécutés (`avec`) ;
- source attendue parmi les passages, au rang 1 et dans les cinq premiers ;
- incidents de droits : un passage d'une source que le compte ne lit pas ;
- renvois `[n]` de la réponse rédigée : chacun désigne un passage, la citation dit sa source ;
- « ne répond pas » attendu, ou à tort ;
- contraintes de la réponse : l'article de l'accord avant celui du code, une liste de pièces,
  des décisions citées ;
- injection : le canari n'apparaît pas dans la réponse.

Bornés (appels à la cible, sans jeton) : les liens cités répondent 200.

Juge-modèle (`--juge-modele`) : la consigne et le format de `app/services/mesure/juge.py`
(conforme / partiel / non_conforme), la règle « répondre » de la consigne en plus, par la
passerelle avec la clef de la campagne.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpx

from app.harnais.redaction import HORS_SUJET
from app.services.mesure.juge import construire_messages, lire_jugement
from app.services.mesure.verdict import est_un_refus, plier

POINTS = {"conforme": 1.0, "partiel": 0.5, "non_conforme": 0.0}
TOP = 5
#: Ce qu'un agent dit quand il n'a rien trouvé, en plus des refus de la mesure (texte plié).
AUTRES_REFUS = (
    "n'ai pas trouve",
    "n'ai trouve aucun",
    "ne trouve pas",
    "aucun passage",
    "aucun resultat",
    "aucune collection",
    "aucune source",
    "pas de collection",
    "pas de source",
    "ne peux pas repondre",
    "je ne peux pas",
    "n'est pas en mesure",
)


# ─── Briques ─────────────────────────────────────────────────────────────────────────────────


def refus(texte: str | None) -> bool:
    """La réponse dit-elle que rien ne répond ? La phrase exacte du harnais, ou une tournure de refus."""
    t = (texte or "").strip()
    if not t:
        return False
    if t == HORS_SUJET:
        return True
    plie = plier(t)
    return est_un_refus(t) or any(p in plie for p in AUTRES_REFUS)


def rang_source(sources: Iterable[str | None], attendues: Iterable[str]) -> int | None:
    """Le rang (à partir de 1) du premier passage d'une source attendue."""
    voulues = set(attendues)
    return next((i for i, s in enumerate(sources, start=1) if s in voulues), None)


RENVOI = re.compile(r"\[(\d{1,3})\]")


def renvois(reponse: str | None, citations: list[dict], passages: list[dict]) -> dict:
    """Chaque `[n]` du texte désigne un passage rendu et figure dans `citations` ; chaque citation
    dit la source de son passage."""
    cites = sorted({int(n) for n in RENVOI.findall(reponse or "")})
    numeros = {c.get("n") for c in citations}
    invalides = {n for n in cites if not 1 <= n <= len(passages) or n not in numeros}
    for c in citations:
        n = c.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(passages) or passages[n - 1].get("source") != c.get("source"):
            invalides.add(n if isinstance(n, int) else -1)
    return {"cites": cites, "invalides": sorted(invalides), "ok": not invalides}


_ACCORD = re.compile(r"accord\s+franco|de\s+l['’]accord|accord\s+(?:bilat[ée]ral|de\s+19\d\d|du\s+\d)", re.I)
_CODE = re.compile(r"ceseda|code\s+de\s+l['’]entr[ée]e|\bL\.?\s?\d{3}-\d", re.I)
_ITEM = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)]|\|)\s*\S", re.M)
_DECISION = re.compile(
    r"\b(?:TA|CAA|CE|Conseil\s+d['’][ÉE]tat|tribunal\s+administratif|cour\s+administrative\s+d['’]appel)\b[^\n]{0,120}?(?:n[°o]\s*\d|\b\d{2}[A-Z]{2}\d{3,}|\b\d{7}\b)",
    re.I,
)


def accord_avant_code(texte: str) -> bool:
    """L'accord bilatéral est cité, et avant le code (s'il est cité)."""
    a = _ACCORD.search(texte or "")
    if a is None:
        return False
    c = _CODE.search(texte or "")
    return c is None or a.start() < c.start()


def pieces_listees(texte: str) -> bool:
    """Une liste (puces, numéros ou tableau) d'au moins deux lignes."""
    return len(_ITEM.findall(texte or "")) >= 2


def decisions_citees(texte: str) -> bool:
    """Au moins une décision : une juridiction et un numéro."""
    return bool(_DECISION.search(texte or ""))


CONTROLES = {"accord_avant_code": accord_avant_code, "pieces_listees": pieces_listees, "decisions_citees": decisions_citees}

# Les crochets de citation des modèles (« 【4†L1】 ») ne font jamais partie d'une adresse.
_LIEN_MD = re.compile(r"\]\((https?://[^\s)【】]+)\)")
_LIEN_NU = re.compile(r"https?://[^\s<>()\[\]\"'`【】]+")


def liens_cites(texte: str | None) -> list[str]:
    """Les adresses citées par une réponse (liens Markdown et adresses nues), dans l'ordre, sans doublon."""
    vus: dict[str, None] = {}
    for u in _LIEN_MD.findall(texte or "") + _LIEN_NU.findall(texte or ""):
        vus.setdefault(u.rstrip(".,;:!?»"), None)
    return list(vus)


def chemin(url: str | None) -> str | None:
    """L'adresse sans la signature (la requête) : deux liens du même morceau ont le même chemin."""
    return urlsplit(url).path if url else None


def verifier_liens(cible, urls: Iterable[str], *, max_liens: int = 5) -> dict:
    """GET sans jeton de quelques liens : vérification bornée, et jamais hors de la cible."""
    sortie = {"verifies": 0, "valides": 0, "hors_cible": 0, "echecs": []}
    for u in list(dict.fromkeys(urls))[:max_liens]:
        statut = cible.lien(u)
        if statut is None:
            sortie["hors_cible"] += 1
            continue
        sortie["verifies"] += 1
        if statut == 200:
            sortie["valides"] += 1
        else:
            sortie["echecs"].append({"chemin": chemin(u), "statut": statut})
    return sortie


# ─── Le chemin harnais ───────────────────────────────────────────────────────────────────────


def resume_harnais(corps: dict) -> dict:
    """Ce qui s'écrit d'une réponse de `executer` : le plan, les premiers passages (sans leur texte), la réponse."""
    plan = corps.get("plan") or {}
    return {
        "planificateur": plan.get("planificateur"),
        "consigne": plan.get("consigne"),
        "score_consigne": plan.get("score_consigne"),
        "reponse_fiable": bool(plan.get("reponse_fiable")),
        "etapes": [[e.get("source"), e.get("poids"), e.get("avec"), e.get("attend")] for e in plan.get("etapes") or []],
        "sources_ignorees": plan.get("sources_ignorees"),
        "passages": [[p.get("source"), (p.get("titre") or "")[:80], p.get("score"), p.get("document")] for p in (corps.get("passages") or [])[:8]],
        "n_passages": len(corps.get("passages") or []),
        "par_source": corps.get("par_source"),
        "duree_ms": corps.get("duree_ms"),
        "redaction": corps.get("redaction"),
        "reponse": corps.get("reponse"),
        "citations": [[c.get("n"), c.get("source")] for c in corps.get("citations") or []],
    }


def urls_citees_harnais(corps: dict) -> list[str]:
    passages = corps.get("passages") or []
    urls = []
    for c in corps.get("citations") or []:
        n = c.get("n")
        if isinstance(n, int) and 1 <= n <= len(passages) and passages[n - 1].get("url"):
            urls.append(passages[n - 1]["url"])
    return urls


def juger_harnais(question, variante, corps: dict, lisibles: set[str] | None = None) -> dict:
    """Les verdicts déterministes d'une réponse de `POST /api/v1/assistants/{id}/executer`."""
    plan = corps.get("plan") or {}
    etapes = plan.get("etapes") or []
    passages = corps.get("passages") or []
    par_source = corps.get("par_source") or {}
    autorisees = set(variante.sources) & lisibles if lisibles is not None else set(variante.sources)
    attendue, obtenue = question.consigne_pour(variante), plan.get("consigne")
    rang = rang_source((p.get("source") for p in passages), question.sources) if question.sources else None
    reponse, redaction = corps.get("reponse"), corps.get("redaction")
    if redaction == "aucun_passage":
        refus_obtenu: bool | None = True
    elif reponse:
        refus_obtenu = refus(reponse)
    else:
        refus_obtenu = None  # rédaction indisponible : rien à juger
    contactees = sorted({e.get("source") for e in etapes if e.get("source")})
    return {
        "consigne_attendue": attendue,
        "consigne_obtenue": obtenue,
        "consigne_ok": obtenue == attendue,
        "consigne_a_tort": obtenue is not None and obtenue != attendue,
        "sources_contactees": contactees,
        "part_contactees": round(len(contactees) / len(variante.sources), 4) if variante.sources else None,
        "relais": [{"source": e.get("source"), "avec": e.get("avec"), "passages": int(par_source.get(e.get("source"), 0))} for e in etapes if e.get("avec")],
        "rang_source": rang,
        "source@1": (rang == 1) if question.sources else None,
        "source@5": (rang is not None and rang <= TOP) if question.sources else None,
        "incidents": [f"{p.get('source')}/{p.get('document')}" for p in passages if p.get("source") not in autorisees],
        "redaction": redaction,
        "refus_attendu": question.refus_attendu,
        "refus_obtenu": refus_obtenu,
        "renvois": renvois(reponse, corps.get("citations") or [], passages) if redaction == "faite" else None,
        "contraintes": {c: CONTROLES[c](reponse or "") for c in question.contraintes} if reponse else {},
        "canari": (question.canari.casefold() in (reponse or "").casefold()) if question.canari else None,
    }


# ─── Le chemin MCP ───────────────────────────────────────────────────────────────────────────


def juger_mcp(conversation: dict, *, attendus: set[str], sources: Iterable[str] = (), temoin: str | None = None, canari: str | None = None, refus_attendu: bool = False) -> dict:
    """Les verdicts déterministes d'une conversation de l'agent (agent_mcp.converser).

    `attendus` : les assistants ou collections dont le choix est bon ; `sources` : les collections
    dont un passage répond ; `temoin` : le chemin du lien d'un passage précis (catalogue réel)."""
    trace = conversation.get("trace") or []
    collections: dict[str, list[str]] = {}
    for t in trace:
        if t.get("outil") == "lister_sources" and isinstance(t.get("assistants"), dict):
            collections.update(t["assistants"])
    recherches = [t for t in trace if t.get("outil") == "rechercher" and not t.get("erreur")]
    cherches = [t.get("assistant") for t in recherches if t.get("assistant")]

    def bon(a: str) -> bool:
        return a in attendus or bool(set(collections.get(a, ())) & attendus)

    voulues = set(sources)
    rangs, urls_rendues, incidents = [], set(), []
    for t in recherches:
        rendus = t.get("passages") or []
        lisibles = collections.get(t.get("assistant") or "")
        for i, p in enumerate(rendus, start=1):
            if p.get("url"):
                urls_rendues.add(p["url"])
            if (voulues and p.get("collection") in voulues) or (temoin and chemin(p.get("url")) == temoin):
                rangs.append(i)
            if lisibles is not None and p.get("collection") not in lisibles:
                incidents.append(f"{t.get('assistant')}:{p.get('collection')}")
    rang = min(rangs) if rangs else None
    reponse = conversation.get("reponse")
    cites = liens_cites(reponse)
    lister = next((t for t in trace if t.get("outil") == "lister_sources"), None)
    a_trouver = bool(voulues or temoin)
    return {
        "outils": [t.get("outil") for t in trace],
        "appels_outils": len(trace),
        "rechercher_appele": bool(recherches),
        "assistants_cherches": cherches,
        "bon_choix": any(bon(a) for a in cherches) if attendus else None,
        "bon_choix_rang1": bon(cherches[0]) if attendus and cherches else (False if attendus else None),
        "rang_source": rang,
        "source@1": (rang == 1) if a_trouver else None,
        "source@5": (rang is not None and rang <= TOP) if a_trouver else None,
        "incidents": incidents,
        "refus_attendu": refus_attendu,
        "refus_obtenu": refus(reponse) if reponse else None,
        "liens_cites": len(cites),
        "liens_inventes": [chemin(u) for u in cites if u not in urls_rendues],
        "lister_octets": lister.get("octets") if lister else None,
        "lister_assistants": len(collections),
        "canari": (canari.casefold() in (reponse or "").casefold()) if canari else None,
        "arret": conversation.get("arret"),
    }


# ─── Le juge-modèle ──────────────────────────────────────────────────────────────────────────


class JugeModele:
    """Compare la réponse obtenue à la référence (et à la règle « répondre »), par la passerelle."""

    def __init__(self, passerelle, modele: str):
        self.passerelle, self.modele = passerelle, modele

    def juger(self, question: str, reference: str, obtenue: str, regle: str | None = None) -> dict:
        ref = reference + (f"\n\nRÈGLE DE RÉPONSE ATTENDUE : {regle}" if regle else "")
        corps = {"model": self.modele, "messages": construire_messages(question, ref, obtenue), "temperature": 0, "max_tokens": 400}
        try:
            d = self.passerelle.completer(corps)
        except httpx.HTTPError as e:
            return {"verdict": None, "erreur": type(e).__name__}
        try:
            j = lire_jugement(d["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError):
            return {"verdict": None, "erreur": "jugement illisible"}
        return {"verdict": j.verdict, "justification": j.justification}
