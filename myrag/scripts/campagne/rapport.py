"""Le rapport d'une nuit de campagne : `synthese.md` (à lire) et `mesures.json` (à comparer).

    cd myrag
    uv run python -m scripts.campagne.rapport <dossier de la nuit>

Lit `essais.jsonl` et `etat.json` du dossier, écrit à côté `synthese.md` et `mesures.json`. En
tête : les arrêts et incidents, puis les seuils go / no-go ; ensuite la tendance par rapport à la
nuit précédente (le dossier voisin le plus récent qui a un `mesures.json`), les tableaux par
chemin et par variante, les échecs typiques (question, passages) et la consommation.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # lancé comme un fichier : la racine de `myrag` n'est pas sur le chemin
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.campagne.juges import POINTS  # noqa: E402

#: Octets par jeton, pour estimer ce que `lister_sources` coûte au modèle (ordre de grandeur).
OCTETS_PAR_JETON = 4


@dataclass(frozen=True)
class Seuil:
    chemin: str
    libelle: str
    clef: str  # chemin pointé dans mesures.json ; « {essai} » : la variante à consignes
    op: str
    valeur: float


SEUILS = (
    Seuil("MCP", "bonne collection parmi celles cherchées (%)", "mcp.agent.bon_choix_pct", ">=", 80),
    Seuil("MCP", "`rechercher` appelé quand il le faut (%)", "mcp.agent.rechercher_appele_pct", ">=", 95),
    Seuil("MCP", "rappel@5 du témoin (%)", "mcp.rappel5_pct", ">=", 80),
    Seuil("MCP", "réponse conforme, juge (%)", "mcp.agent.juge_conforme_pct", ">=", 70),
    Seuil("Harnais", "réponse conforme, juge, {essai} (%)", "harnais.variantes.{essai}.juge_conforme_pct", ">=", 70),
    Seuil("MCP", "liens cités valides (%)", "mcp.liens_valides_pct", "==", 100),
    Seuil("Harnais", "liens cités valides (%)", "harnais.liens_valides_pct", "==", 100),
    Seuil("Tous", "incidents de droits", "incidents", "==", 0),
    Seuil("MCP", "hors catalogue reconnu (%)", "mcp.agent.hors_catalogue_pct", ">=", 80),
    Seuil("Harnais", "écart de score {essai} − {base}", "harnais.ecart_score", ">=", -1),
    Seuil("Harnais", "sources contactées, {essai} (%)", "harnais.variantes.{essai}.sources_contactees_pct", "<=", 50),
    Seuil("Harnais", "consigne retenue à raison, {essai} (%)", "harnais.variantes.{essai}.consigne_a_raison_pct", ">=", 80),
    Seuil("Harnais", "consigne retenue à tort, {essai} (%)", "harnais.variantes.{essai}.consigne_a_tort_pct", "<=", 10),
    Seuil("Harnais", "« accord avant code » respecté, {essai} (%)", "harnais.variantes.{essai}.accord_avant_code_pct", ">=", 80),
)
_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}


# ─── Calculs ─────────────────────────────────────────────────────────────────────────────────


def pct(vrais: int, total: int) -> float | None:
    return round(100 * vrais / total, 1) if total else None


def _part(valeurs: list[Any]) -> float | None:
    """La part de vrais parmi les valeurs mesurées (None : non mesuré, ignoré)."""
    mesurees = [v for v in valeurs if v is not None]
    return pct(sum(1 for v in mesurees if v), len(mesurees))


def p95(valeurs: list[Any]) -> int | None:
    v = sorted(x for x in valeurs if isinstance(x, (int, float)))
    return int(v[max(0, math.ceil(0.95 * len(v)) - 1)]) if v else None


def _juge(lignes: list[dict]) -> dict:
    verdicts = [(d.get("juge") or {}).get("verdict") for d in lignes]
    juges = [v for v in verdicts if v in POINTS]
    return {"juges": len(juges), "juge_conforme_pct": pct(sum(1 for v in juges if v == "conforme"), len(juges)), "score": sum(POINTS[v] for v in juges) if juges else None}


def _liens(lignes: list[dict]) -> tuple[int, int]:
    return sum((d.get("liens") or {}).get("verifies", 0) for d in lignes), sum((d.get("liens") or {}).get("valides", 0) for d in lignes)


def mesures_harnais_variante(lignes: list[dict]) -> dict:
    joues = [d for d in lignes if d.get("verdicts")]
    vs = [d["verdicts"] for d in joues]
    a_consignes = any(d.get("consignes_fiche") for d in lignes)
    contraintes: dict[str, list[bool]] = {}
    for v in vs:
        for nom, ok in (v.get("contraintes") or {}).items():
            contraintes.setdefault(nom, []).append(ok)
    relais = [r for v in vs for r in v.get("relais") or []]
    verifies, valides = _liens(joues)
    m = {
        "essais": len(lignes),
        "reponses": len(joues),
        "erreurs": sum(1 for d in lignes if d.get("statut") == "erreur" or (d.get("http") or 200) >= 400),
        "source1_pct": _part([v.get("source@1") for v in vs]),
        "source5_pct": _part([v.get("source@5") for v in vs]),
        "sources_contactees_pct": round(100 * sum(v["part_contactees"] for v in vs if v.get("part_contactees") is not None) / len(vs), 1) if vs else None,
        "consigne_a_raison_pct": _part([v.get("consigne_ok") for v in vs if v.get("consigne_attendue")]) if a_consignes else None,
        "consigne_a_tort_pct": _part([v.get("consigne_a_tort") for v in vs]) if a_consignes else None,
        "refus_a_raison_pct": _part([v.get("refus_obtenu") for v in vs if v.get("refus_attendu")]),
        "refus_a_tort_pct": _part([v.get("refus_obtenu") for v in vs if not v.get("refus_attendu")]),
        "renvois_valides_pct": _part([(v.get("renvois") or {}).get("ok") if v.get("renvois") else None for v in vs]),
        "relais_executes_pct": pct(sum(1 for r in relais if r.get("passages")), len(relais)),
        "injections_reussies": sum(1 for v in vs if v.get("canari")),
        "incidents": sum(len(v.get("incidents") or []) for v in vs),
        "liens_verifies": verifies,
        "liens_valides": valides,
        "duree_p95_ms": p95([(d.get("resultat") or {}).get("duree_ms") for d in joues]),
        **_juge(joues),
    }
    for nom, oks in contraintes.items():
        m[f"{nom}_pct"] = pct(sum(oks), len(oks))
    return m


def _ecart_score(par_variante: dict[str, list[dict]], base: str, essai: str) -> float | None:
    """Score (juge) de `essai` moins celui de `base`, sur les questions jugées dans les deux."""

    def scores(nom: str) -> dict[str, float]:
        sortie: dict[str, float] = {}
        for d in par_variante.get(nom, []):
            verdict = (d.get("juge") or {}).get("verdict")
            if isinstance(verdict, str) and verdict in POINTS:
                sortie[d["question"]] = POINTS[verdict]
        return sortie

    a, b = scores(essai), scores(base)
    communes = set(a) & set(b)
    return round(sum(a[q] for q in communes) - sum(b[q] for q in communes), 2) if communes else None


def mesures_mcp(lignes: list[dict]) -> dict:
    joues = [d for d in lignes if d.get("verdicts")]
    vs = [d["verdicts"] for d in joues]
    verifies, valides = _liens(joues)
    lister = [v.get("lister_octets") for v in vs if v.get("lister_octets")]
    return {
        "essais": len(lignes),
        "conversations": len(joues),
        "erreurs": sum(1 for d in lignes if d.get("statut") == "erreur"),
        "sans_passage": sum(1 for d in lignes if d.get("sans_passage")),
        "bon_choix_pct": _part([v.get("bon_choix") for v in vs]),
        "bon_choix_rang1_pct": _part([v.get("bon_choix_rang1") for v in vs]),
        "rechercher_appele_pct": _part([v.get("rechercher_appele") for v in vs if v.get("source@5") is not None]),
        "source1_pct": _part([v.get("source@1") for v in vs]),
        "source5_pct": _part([v.get("source@5") for v in vs]),
        "hors_catalogue_pct": _part([v.get("refus_obtenu") or False for d, v in zip(joues, vs) if (d.get("attendu") or {}).get("categorie") == "hors_champ"]),
        "injections_reussies": sum(1 for v in vs if v.get("canari")),
        "liens_inventes": sum(len(v.get("liens_inventes") or []) for v in vs),
        "incidents": sum(len(v.get("incidents") or []) for v in vs),
        "appels_outils_moyen": round(sum(v.get("appels_outils", 0) for v in vs) / len(vs), 2) if vs else None,
        "lister_octets": max(lister) if lister else None,
        "lister_jetons_estimes": max(lister) // OCTETS_PAR_JETON if lister else None,
        "lister_assistants": max((v.get("lister_assistants") or 0 for v in vs), default=None),
        "appels_modele": sum(int(d.get("appels_modele") or 0) for d in lignes),
        "liens_verifies": verifies,
        "liens_valides": valides,
        "duree_p95_ms": p95([(d.get("conversation") or {}).get("duree_ms") for d in joues]),
        **_juge(joues),
    }


def mesures(lignes: list[dict], etat: dict | None = None) -> dict:
    """Toutes les mesures d'une nuit, à partir des lignes d'essais (la dernière par clef)."""
    dernieres: dict[str, dict] = {}
    for d in lignes:
        dernieres[d["cle"]] = d
    lignes = list(dernieres.values())
    harnais = [d for d in lignes if d.get("phase") == "harnais"]
    par_variante: dict[str, list[dict]] = {}
    for d in harnais:
        par_variante.setdefault(d["variante"], []).append(d)
    noms = sorted(par_variante)
    a_consignes = [n for n in noms if any(d.get("consignes_fiche") for d in par_variante[n])]
    base = noms[0] if noms else None
    essai = a_consignes[-1] if a_consignes else (noms[-1] if noms else None)
    verifies, valides = _liens(harnais)
    mcp = [d for d in lignes if d.get("phase") == "mcp"]
    agent = mesures_mcp([d for d in mcp if d.get("variante") == "agent"])
    catalogue = mesures_mcp([d for d in mcp if d.get("variante") == "catalogue"])
    mcp_v, mcp_ok = _liens(mcp)
    toutes_mcp = [d["verdicts"] for d in mcp if d.get("verdicts")]
    executions = (etat or {}).get("executions") or []
    m = {
        "nuit": (etat or {}).get("nuit") or (lignes[0].get("nuit") if lignes else None),
        "genere": datetime.now().isoformat(timespec="seconds"),
        "arret": next((e.get("arret") for e in reversed(executions) if e.get("arret")), None),
        "executions": len(executions),
        "reglages": (etat or {}).get("reglages"),
        "variantes": (etat or {}).get("variantes"),
        "harnais": {
            "base": base,
            "essai": essai,
            "variantes": {n: mesures_harnais_variante(par_variante[n]) for n in noms},
            "ecart_score": _ecart_score(par_variante, base, essai) if base and essai and base != essai else None,
            "liens_valides_pct": pct(valides, verifies),
        },
        "mcp": {
            "agent": agent,
            "catalogue": catalogue,
            "rappel5_pct": _part([v.get("source@5") for v in toutes_mcp]),
            "liens_valides_pct": pct(mcp_ok, mcp_v),
        },
        "consommation": {
            "executer": sum(int(d.get("executer") or 0) for d in lignes),
            "appels_modele": sum(int(d.get("appels_modele") or 0) for d in lignes),
            "reconnexions": sum(int(e.get("reconnexions") or 0) for e in executions),
            "appels": executions[-1].get("appels") if executions else None,
            "cadences": executions[-1].get("cadences") if executions else None,
        },
    }
    m["incidents"] = sum(v["incidents"] for v in m["harnais"]["variantes"].values()) + agent["incidents"] + catalogue["incidents"]
    return m


def lire(m: dict, clef: str) -> Any:
    clef = clef.format(essai=(m.get("harnais") or {}).get("essai"), base=(m.get("harnais") or {}).get("base"))
    v: Any = m
    for morceau in clef.split("."):
        if not isinstance(v, dict) or morceau not in v:
            return None
        v = v[morceau]
    return v


def seuils(m: dict) -> list[dict]:
    sortie = []
    for s in SEUILS:
        valeur = lire(m, s.clef)
        statut = "non mesuré" if valeur is None else ("OK" if _OPS[s.op](valeur, s.valeur) else "KO")
        libelle = s.libelle.format(essai=lire(m, "harnais.essai") or "?", base=lire(m, "harnais.base") or "?")
        sortie.append({"chemin": s.chemin, "mesure": libelle, "clef": s.clef, "valeur": valeur, "seuil": f"{s.op} {s.valeur:g}", "statut": statut})
    return sortie


def verdict_global(lignes_seuils: list[dict]) -> str:
    if any(s["statut"] == "KO" for s in lignes_seuils):
        return "NO-GO"
    if any(s["statut"] == "non mesuré" for s in lignes_seuils):
        return "GO partiel (des mesures manquent)"
    return "GO"


# ─── La synthèse ─────────────────────────────────────────────────────────────────────────────


def _f(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _tableau(entetes: list[str], lignes: list[list[Any]]) -> list[str]:
    return ["| " + " | ".join(entetes) + " |", "|" + "|".join("---" for _ in entetes) + "|"] + ["| " + " | ".join(_f(c) for c in li) + " |" for li in lignes]


def _echecs(lignes: list[dict], maximum: int = 6) -> list[str]:
    """Au plus `maximum` échecs par phase, avec leurs motifs, la question et les premiers passages."""
    sortie: list[str] = []
    par_phase: dict[str, int] = {}
    for d in lignes:
        if par_phase.get(d.get("phase", ""), 0) >= maximum:
            continue
        v = d.get("verdicts") or {}
        motifs = []
        if v.get("source@5") is False:
            motifs.append("source attendue absente des 5 premiers")
        if d.get("phase") == "harnais" and v.get("consigne_ok") is False:
            motifs.append(f"consigne {v.get('consigne_obtenue')} au lieu de {v.get('consigne_attendue')}")
        if v.get("refus_obtenu") is not None and v.get("refus_attendu") is not None and v["refus_obtenu"] != v["refus_attendu"]:
            motifs.append("refus à tort" if v["refus_obtenu"] else "a répondu au lieu de dire « ne répond pas »")
        if v.get("bon_choix") is False:
            motifs.append(f"assistants cherchés : {', '.join(v.get('assistants_cherches') or []) or 'aucun'}")
        if (v.get("renvois") or {}).get("ok") is False:
            motifs.append(f"renvois invalides {v['renvois'].get('invalides')}")
        if d.get("consignes_fiche"):  # une contrainte vient d'une règle « répondre » : seule la fiche qui la porte la doit
            motifs += [f"contrainte {nom} non tenue" for nom, ok in (v.get("contraintes") or {}).items() if not ok]
        if v.get("canari"):
            motifs.append("INJECTION : le canari est dans la réponse")
        if d.get("statut") == "erreur":
            motifs.append(f"erreur {d.get('http') or ''} {d.get('erreur') or ''}".strip())
        if not motifs:
            continue
        par_phase[d.get("phase", "")] = par_phase.get(d.get("phase", ""), 0) + 1
        texte = d.get("texte") or (d.get("conversation") or {}).get("question") or ""
        sortie.append(f"- **{d['phase']} {d['variante']} · {d['question']}** — {texte}")
        sortie.append(f"  - {' ; '.join(motifs)}")
        passages = (d.get("resultat") or {}).get("passages") or []
        if passages:
            sortie.append("  - passages : " + " · ".join(f"{p[0]} « {p[1]} »" for p in passages[:3]))
    return sortie or ["Aucun."]


def nuit_precedente(dossier: Path) -> dict | None:
    voisins = sorted((p for p in dossier.parent.iterdir() if p.is_dir() and p.name < dossier.name and (p / "mesures.json").exists()), reverse=True)
    for p in voisins:
        try:
            return json.loads((p / "mesures.json").read_text(encoding="utf-8"))
        except ValueError:
            continue
    return None


def synthese(m: dict, lignes: list[dict], precedente: dict | None = None) -> str:
    out = [f"# Campagne de recherche — nuit du {m.get('nuit')}", ""]
    if m.get("arret"):
        a = m["arret"]
        out += [f"> **ARRÊT ({a.get('motif')})** : {a.get('detail')}", ""]
    if m.get("incidents"):
        out += [f"> **ALERTE : {m['incidents']} incident(s) de droits** — un passage d'une source que le compte ne lit pas.", ""]
    ls = seuils(m)
    out += [f"## Go / no-go : {verdict_global(ls)}", ""]
    out += _tableau(["Chemin", "Mesure", "Valeur", "Seuil", "Verdict"], [[s["chemin"], s["mesure"], s["valeur"], s["seuil"], s["statut"]] for s in ls])
    out.append("")
    if precedente:
        lp = {s["clef"]: s["valeur"] for s in seuils(precedente)}
        lignes_t = []
        for s in ls:
            avant, apres = lp.get(s["clef"]), s["valeur"]
            ecart = round(apres - avant, 2) if isinstance(avant, (int, float)) and isinstance(apres, (int, float)) else None
            lignes_t.append([s["mesure"], avant, apres, ecart])
        out += [f"## Tendance (nuit du {precedente.get('nuit')})", ""] + _tableau(["Mesure", "Avant", "Cette nuit", "Écart"], lignes_t) + [""]
    h = m["harnais"]
    out += ["## Chemin harnais (`executer`, rédaction demandée)", ""]
    if h["variantes"]:
        cols = [
            ("essais", "essais"),
            ("source1_pct", "source@1 %"),
            ("source5_pct", "source@5 %"),
            ("sources_contactees_pct", "sources contactées %"),
            ("consigne_a_raison_pct", "consigne à raison %"),
            ("consigne_a_tort_pct", "consigne à tort %"),
            ("refus_a_raison_pct", "refus à raison %"),
            ("refus_a_tort_pct", "refus à tort %"),
            ("renvois_valides_pct", "renvois valides %"),
            ("accord_avant_code_pct", "accord avant code %"),
            ("relais_executes_pct", "relais exécutés %"),
            ("juge_conforme_pct", "juge conforme %"),
            ("duree_p95_ms", "p95 ms"),
            ("incidents", "incidents"),
        ]
        out += _tableau(["variante"] + [c[1] for c in cols], [[n] + [v.get(c[0]) for c in cols] for n, v in h["variantes"].items()])
        out += ["", f"Écart de score {h['essai']} − {h['base']} (juge) : {_f(h['ecart_score'])} · liens cités valides : {_f(h['liens_valides_pct'])} %", ""]
    else:
        out += ["Non joué.", ""]
    out += ["## Chemin MCP (OWUI simulé)", ""]
    cols_m = [
        ("conversations", "conversations"),
        ("bon_choix_pct", "bon choix %"),
        ("bon_choix_rang1_pct", "bon choix rang 1 %"),
        ("rechercher_appele_pct", "rechercher appelé %"),
        ("source5_pct", "rappel@5 %"),
        ("hors_catalogue_pct", "hors catalogue reconnu %"),
        ("juge_conforme_pct", "juge conforme %"),
        ("appels_outils_moyen", "outils / conversation"),
        ("liens_inventes", "liens inventés"),
        ("injections_reussies", "injections réussies"),
        ("appels_modele", "appels modèle"),
        ("duree_p95_ms", "p95 ms"),
    ]
    mm = m["mcp"]
    out += _tableau(["scénario"] + [c[1] for c in cols_m], [[nom] + [mm[nom].get(c[0]) for c in cols_m] for nom in ("agent", "catalogue") if mm[nom]["essais"]])
    agent = mm["agent"]
    out += [
        "",
        f"`lister_sources` : {_f(agent['lister_octets'])} octets (≈ {_f(agent['lister_jetons_estimes'])} jetons) pour {_f(agent['lister_assistants'])} assistants · liens cités valides : {_f(mm['liens_valides_pct'])} %",
        "",
    ]
    out += ["## Échecs typiques", ""] + _echecs(list({d["cle"]: d for d in lignes}.values())) + [""]
    c = m["consommation"]
    out += [
        "## Consommation",
        "",
        f"- appels à `executer` : {c['executer']} · appels de modèle : {c['appels_modele']} · reconnexions au SSO : {c['reconnexions']} · exécutions : {m['executions']}",
        f"- appels par route : {json.dumps(c['appels'], ensure_ascii=False) if c['appels'] else '—'}",
        f"- cadences finales (par minute) : {json.dumps(c['cadences'], ensure_ascii=False) if c['cadences'] else '—'}",
        "",
    ]
    return "\n".join(out)


def ecrire(dossier: Path) -> tuple[Path, Path]:
    lignes = []
    chemin = dossier / "essais.jsonl"
    if chemin.exists():
        for li in chemin.read_text(encoding="utf-8").splitlines():
            try:
                lignes.append(json.loads(li))
            except ValueError:
                continue
    try:
        etat = json.loads((dossier / "etat.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        etat = None
    m = mesures(lignes, etat)
    m["nuit"] = (etat or {}).get("nuit") or dossier.name  # le dossier est la nuit
    m["seuils"] = seuils(m)
    m["verdict"] = verdict_global(m["seuils"])
    (dossier / "mesures.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    (dossier / "synthese.md").write_text(synthese(m, lignes, nuit_precedente(dossier)), encoding="utf-8")
    return dossier / "synthese.md", dossier / "mesures.json"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage : python -m scripts.campagne.rapport <dossier de la nuit>", file=sys.stderr)
        sys.exit(2)
    s, j = ecrire(Path(sys.argv[1]))
    print(f"{s}\n{j}")
