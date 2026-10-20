"""Le banc des assistants : sans HTTP ni réseau, un planificateur choisit-il les bonnes sources ?

`jouer` pose chaque question d'un jeu à un planificateur, exécute son plan, fait juger les passages
rendus et mesure : rappel du passage témoin (rang 1, rang ≤ 5), part des sources contactées, score,
incidents de droits (un passage d'une source que la personne ne lit pas) et durée. Deux
planificateurs se comparent sur le même jeu (`verifier` rapproche le rapport d'une ligne de base).

    uv run python -m scripts.banc tests/harnais/fixtures/banc/sejour-des-etrangers.json \
        --juge doublure --planificateur regles --rapport json

Le juge « doublure » est déterministe. Le juge « réel » (un modèle, via la passerelle) n'est pas
branché : il demandera la passerelle de modèle et un compte (docs/assistants.md, « Le banc »)."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import math
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal

if __package__ in (None, ""):  # lancé comme un fichier : la racine de `myrag` n'est pas sur le chemin
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harnais import execution as harnais_execution
from app.harnais import perimetre
from app.harnais.apparieur import ApparieurSacDeMots
from app.harnais.contrat import Appelant, Contexte, Etape, FicheAssistant, FicheSource, Passage, Plan
from app.harnais.fusion import fusionner
from app.harnais.interfaces import Connecteur, Planificateur
from app.harnais.plan.regles import Regles
from app.harnais.plan.toutes_les_sources import ToutesLesSources

Verdict = Literal["conforme", "partiel", "non_conforme"]
POINTS: dict[str, float] = {"conforme": 1.0, "partiel": 0.5, "non_conforme": 0.0}
#: Les passages montrés au juge : le rappel@5 se joue sur ces cinq-là.
TOP_JUGE = 5
TOP_K = 10
PLANIFICATEURS = ("toutes_les_sources", "regles")


@dataclass(frozen=True)
class Question:
    id: str
    texte: str
    identite: str
    #: La source visée (son témoin est le passage attendu) ; `None` : question de droits, sans passage attendu.
    source: str | None = None


@dataclass(frozen=True)
class Identite:
    """Une personne du jeu : son appelant, et ce qu'elle lit VRAIMENT (le banc compte les fuites contre cette liste)."""

    appelant: Appelant
    lisibles: tuple[str, ...]


@dataclass
class SortieBanc:
    """Ce que rend l'exécution d'un plan : le plan tel qu'il a été exécuté et les passages fusionnés."""

    plan: Plan
    passages: list[Passage]


Executeur = Callable[[Plan, Identite], Awaitable[SortieBanc]]
Juge = Callable[[Question, Sequence[Passage]], "Verdict | Awaitable[Verdict]"]


@dataclass
class ResultatQuestion:
    id: str
    identite: str
    source: str | None
    verdict: Verdict | None
    rang_temoin: int | None
    sources_contactees: int
    sources_lisibles: int
    incidents: int
    duree_ms: int
    passages: list[str] = field(default_factory=list)  # « source/document », pour comparer deux planificateurs


@dataclass
class Rapport:
    planificateur: str
    resultats: list[ResultatQuestion]

    @property
    def notees(self) -> list[ResultatQuestion]:
        """Les questions qui attendent un témoin (les questions de droits n'entrent pas dans les moyennes)."""
        return [r for r in self.resultats if r.source is not None]

    def rappel(self, k: int) -> float:
        notees = self.notees
        return sum(1 for r in notees if r.rang_temoin is not None and r.rang_temoin <= k) / len(notees) if notees else 0.0

    @property
    def score(self) -> float:
        return sum(POINTS[r.verdict] for r in self.notees if r.verdict)

    @property
    def sources_contactees_pct(self) -> float:
        notees = [r for r in self.notees if r.sources_lisibles]
        return 100 * sum(r.sources_contactees / r.sources_lisibles for r in notees) / len(notees) if notees else 0.0

    @property
    def incidents_droits(self) -> int:
        return sum(r.incidents for r in self.resultats)

    @property
    def duree_p95_ms(self) -> int:
        durees = sorted(r.duree_ms for r in self.resultats)
        return durees[max(0, math.ceil(0.95 * len(durees)) - 1)] if durees else 0

    def mesures(self) -> dict[str, float]:
        return {
            "rappel@1": round(self.rappel(1), 4),
            "rappel@5": round(self.rappel(5), 4),
            "sources_contactees_pct": round(self.sources_contactees_pct, 2),
            "score": self.score,
            "incidents_droits": self.incidents_droits,
            "duree_p95_ms": self.duree_p95_ms,
        }

    def en_dict(self, base: Rapport | None = None) -> dict[str, Any]:
        mesures = self.mesures()
        if base is not None:
            mesures["ecart_score_vs_toutes"] = self.score - base.score
        return {"planificateur": self.planificateur, "mesures": mesures, "questions": [asdict(r) for r in self.resultats]}


async def _attendre(valeur: Any) -> Any:
    return await valeur if inspect.isawaitable(valeur) else valeur


async def jouer(
    assistant: FicheAssistant,
    questions: Sequence[Question],
    *,
    executer: Executeur,
    juger: Juge,
    identites: Mapping[str, Identite],
    planificateur: Planificateur,
    droits: bool = True,
) -> Rapport:
    """Pose chaque question à `planificateur`. `droits=False` neutralise le périmètre côté plan
    (le planificateur voit toutes les sources) : c'est le témoin négatif du banc — avec un
    exécuteur qui ne filtre pas non plus, le banc doit compter des incidents."""
    resultats: list[ResultatQuestion] = []
    toutes = tuple(s.id for s in assistant.sources_ordonnees())
    for q in questions:
        ident = identites[q.identite]
        vues = list(ident.lisibles) if droits else list(toutes)
        debut = time.monotonic()
        plan = await planificateur.plan(assistant, q.texte, Contexte(canal="banc", sources_lisibles=vues, top_k=TOP_K))
        sortie = await executer(plan, ident)
        duree_ms = int((time.monotonic() - debut) * 1000)
        passages = sortie.passages
        verdict: Verdict | None = None
        rang: int | None = None
        if q.source is not None:
            verdict = await _attendre(juger(q, passages[:TOP_JUGE]))
            rang = next((i for i, p in enumerate(passages, start=1) if p.source == q.source and p.meta.get("temoin")), None)
        resultats.append(
            ResultatQuestion(
                id=q.id,
                identite=q.identite,
                source=q.source,
                verdict=verdict,
                rang_temoin=rang,
                sources_contactees=len({e.source for e in sortie.plan.etapes}),
                sources_lisibles=len(ident.lisibles),
                incidents=sum(1 for p in passages if p.source not in ident.lisibles),
                duree_ms=duree_ms,
                passages=[f"{p.source}/{p.document}" for p in passages],
            )
        )
    return Rapport(planificateur=planificateur.nom, resultats=resultats)


def verifier(rapport: Rapport, seuils: Mapping[str, Mapping[str, Any]], base: Rapport | None = None) -> list[str]:
    """Les seuils non tenus, en clair (liste vide : le banc passe). `base` : la ligne de base (toutes les sources)."""
    mesures = rapport.mesures()
    if base is not None:
        mesures["ecart_score_vs_toutes"] = rapport.score - base.score
    manques = []
    for nom, regle in seuils.items():
        if regle.get("bloquant", True) is False or nom not in mesures:
            continue
        if "min" in regle and mesures[nom] < regle["min"]:
            manques.append(f"{nom} = {mesures[nom]} < {regle['min']}")
        if "max" in regle and mesures[nom] > regle["max"]:
            manques.append(f"{nom} = {mesures[nom]} > {regle['max']}")
    return manques


# ---------------------------------------------------------------------------
# Le jeu : fiche, collections d'exemple, personnes, questions
# ---------------------------------------------------------------------------


@dataclass
class Jeu:
    assistant: FicheAssistant
    collections: dict[str, dict]
    identites: dict[str, Identite]
    questions: list[Question]

    @property
    def temoins(self) -> dict[str, str]:
        """source → document témoin (un seul par source)."""
        return {s: next(d["document"] for d in c["documents"] if d.get("temoin")) for s, c in self.collections.items()}

    def descriptions(self) -> dict[str, str]:
        return {s: f"{c['titre']}. {c['description']}" for s, c in self.collections.items()}


def charger_jeu(chemin: Path | str) -> Jeu:
    brut = json.loads(Path(chemin).read_text(encoding="utf-8"))
    fiche = FicheAssistant.model_validate(brut["assistant"])
    collections: dict[str, dict] = brut["collections"]
    for s, c in collections.items():
        if sum(1 for d in c["documents"] if d.get("temoin")) != 1:
            raise ValueError(f"la source « {s} » doit avoir exactement un passage témoin")
    fiches = {s: {"name": s, "scope": c.get("scope"), "scope_groups": c.get("scope_groups"), "created_by": c.get("created_by")} for s, c in collections.items()}
    identites = {}
    for nom, i in brut["identites"].items():
        lisibles = perimetre.sources_lisibles(fiche, fiches, groupes=i["groupes"], sub=i["sub"])
        identites[nom] = Identite(Appelant(sub=i["sub"], groupes=i["groupes"]), tuple(lisibles))
    questions = [Question(q["id"], q["texte"], q["identite"], q.get("source")) for q in brut["questions"]]
    return Jeu(fiche, collections, identites, questions)


class ConnecteurJeu(Connecteur):
    """Une collection d'exemple : classe ses documents par ressemblance (sac de mots) à la question."""

    type: ClassVar[str] = "collection"

    def __init__(self, source: str, documents: Sequence[dict]):
        self.source, self.documents = source, list(documents)
        self.appels = 0

    async def chercher(self, etape: Etape, identite: Appelant, *, amont: Sequence[Passage] = ()) -> list[Passage]:
        self.appels += 1
        par_id = {d["document"]: d for d in self.documents}
        classes = await ApparieurSacDeMots().apparier(etape.question, [(d["document"], f"{d['titre']} {d['texte']}") for d in self.documents])
        return [
            Passage(
                source=self.source,
                etape=etape.n,
                rang=i,
                score=score,
                ident=f"{doc}-1",
                document=doc,
                titre=par_id[doc]["titre"],
                texte=par_id[doc]["texte"],
                meta={"temoin": bool(par_id[doc].get("temoin"))},
            )
            for i, (doc, score) in enumerate(classes, start=1)
        ]

    async def fiche(self) -> FicheSource:
        return FicheSource(id=self.source, type="collection", titre=self.source)


def executeur(jeu: Jeu, *, filtrer: bool = True) -> Executeur:
    """L'exécution du service des assistants, sans la base : le plan est ramené au périmètre de la
    personne, exécuté, fusionné, et les passages hors périmètre sont retirés. `filtrer=False` retire
    ces deux garde-fous (témoin négatif du banc)."""
    connecteurs = {s: ConnecteurJeu(s, c["documents"]) for s, c in jeu.collections.items()}

    async def _executer(plan: Plan, ident: Identite) -> SortieBanc:
        if filtrer:
            plan = perimetre.restreindre_plan(plan, ident.lisibles)
        execution = await harnais_execution.executer(plan, connecteurs, ident.appelant)
        toujours = {s.id for s in jeu.assistant.sources if s.regime == "toujours"}
        passages = fusionner(execution.par_etape, {e.n: e.poids for e in plan.etapes}, toujours=toujours, limite=TOP_K)
        if filtrer:
            passages = perimetre.restreindre_passages(passages, ident.lisibles)
        return SortieBanc(plan, passages)

    return _executer


def juge_doublure(temoins: Mapping[str, str]) -> Juge:
    """Déterministe : conforme si le témoin attendu est rendu, partiel si c'est le témoin d'une autre source, sinon non conforme."""
    tous = {(s, d) for s, d in temoins.items()}

    def _juger(question: Question, passages: Sequence[Passage]) -> Verdict:
        rendus = {(p.source, p.document) for p in passages}
        if (question.source, temoins.get(question.source or "")) in rendus:
            return "conforme"
        return "partiel" if rendus & tous else "non_conforme"

    return _juger


def juge_reel(*_: Any, **__: Any) -> Juge:
    raise NotImplementedError("le juge réel demande la passerelle de modèle et un compte : il n'est pas branché (docs/assistants.md, « Le banc »)")


def planificateur_du_jeu(nom: str, jeu: Jeu) -> Planificateur:
    if nom == "toutes_les_sources":
        return ToutesLesSources()
    if nom == "regles":
        return Regles(ApparieurSacDeMots(), descriptions=jeu.descriptions())
    raise ValueError(f"planificateur inconnu : {nom} (attendus : {', '.join(PLANIFICATEURS)})")


async def jouer_jeu(jeu: Jeu, planificateur: str, juge: str = "doublure", *, droits: bool = True) -> Rapport:
    """Le jeu complet pour un planificateur, avec les garde-fous de droits (ou sans, si `droits=False`)."""
    juger = juge_doublure(jeu.temoins) if juge == "doublure" else juge_reel()
    return await jouer(
        jeu.assistant,
        jeu.questions,
        executer=executeur(jeu, filtrer=droits),
        juger=juger,
        identites=jeu.identites,
        planificateur=planificateur_du_jeu(planificateur, jeu),
        droits=droits,
    )


def charger_seuils(chemin: Path | str) -> dict[str, dict]:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


SEUILS_PAR_DEFAUT = Path(__file__).resolve().parents[1] / "tests" / "harnais" / "fixtures" / "banc" / "seuils.json"


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Le banc des assistants : choisit-on les bonnes sources ?")
    p.add_argument("jeu", help="un jeu figé (tests/harnais/fixtures/banc/*.json)")
    p.add_argument("--juge", choices=("doublure", "reel"), default="doublure")
    p.add_argument("--planificateur", choices=PLANIFICATEURS, default="regles")
    p.add_argument("--rapport", choices=("json", "texte"), default="texte")
    p.add_argument("--seuils", default=str(SEUILS_PAR_DEFAUT))
    args = p.parse_args(argv)
    jeu = charger_jeu(args.jeu)
    try:
        rapport = asyncio.run(jouer_jeu(jeu, args.planificateur, args.juge))
        base = rapport if args.planificateur == "toutes_les_sources" else asyncio.run(jouer_jeu(jeu, "toutes_les_sources", args.juge))
    except NotImplementedError as e:
        print(f"banc : {e}", file=sys.stderr)
        return 2
    manques = verifier(rapport, charger_seuils(args.seuils), base)
    if args.rapport == "json":
        print(json.dumps({**rapport.en_dict(base), "seuils_manques": manques}, ensure_ascii=False, indent=2))
    else:
        for nom, valeur in {**rapport.mesures(), "ecart_score_vs_toutes": rapport.score - base.score}.items():
            print(f"{nom:<24}{valeur}")
        print("seuils : " + ("tenus" if not manques else "; ".join(manques)))
    return 1 if manques else 0


if __name__ == "__main__":
    raise SystemExit(main())
