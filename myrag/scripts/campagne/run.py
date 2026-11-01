"""Le lanceur de la campagne de nuit : reprenable, borné, et qui s'arrête de lui-même.

    cd myrag
    uv run --with playwright python -m scripts.campagne.run --cible https://mycollections.fake-domain.name \
        [--phases harnais,mcp] [--fenetre 21h-6h | maintenant] [--max-executer 300] [--max-appels-modele 400] \
        [--juge-modele <modèle>] [--catalogue 10]

- Reprise : chaque essai s'écrit dans `essais.jsonl`, sous la clef (phase, variante, question,
  nuit) ; un essai déjà joué ne se rejoue pas (une erreur serveur, si : elle n'a rien mesuré).
- Fenêtre : 21 h – 6 h par défaut ; hors fenêtre on attend son ouverture, à sa fermeture on
  s'arrête. `maintenant` : tout de suite, sans fenêtre.
- Budgets par nuit : appels à `executer` (`--max-executer`) et au modèle (`--max-appels-modele`,
  agent, juge et questions du catalogue ensemble). Atteint : la phase s'arrête proprement.
- Règles d'arrêt (cible.Garde) : un incident de droits arrête tout ; plus de 20 % de 5xx sur 50
  appels arrête la nuit ; une rafale de 429 divise la cadence par deux, une seconde arrête la nuit.
  Le même arrêt trois nuits de suite arrête la campagne : la nuit suivante ne démarre pas
  (`--forcer` pour passer outre, après correction).

Variables : CAMPAGNE_CIBLE, CAMPAGNE_SSO_HOST, KC_TEST_IN_USERNAME / _PASSWORD,
CAMPAGNE_CORRESPONDANCE, CAMPAGNE_GATEWAY_URL / _TOKEN (phase mcp et juge-modèle),
CAMPAGNE_RAPPORTS. Mode d'emploi : docs/campagne-recherche.md.

Codes de sortie : 0 nuit jouée (ou bornée par un budget, une fenêtre) ; 2 usage ; 3 règle d'arrêt ;
4 campagne arrêtée (même arrêt trois nuits de suite).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as heure
from pathlib import Path
from typing import Any

import httpx

if __package__ in (None, ""):  # lancé comme un fichier : la racine de `myrag` n'est pas sur le chemin
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.campagne import juges, rapport  # noqa: E402
from scripts.campagne.agent_mcp import MAX_TOURS, MODELE, Agent  # noqa: E402
from scripts.campagne.cible import Arret, BudgetEpuise, Cible, ErreurMcp, Passerelle, Usage, connexion_navigateur, origine  # noqa: E402
from scripts.campagne.corpus import JEU_DEFAUT, PREFIXE, CorpusInvalide, Question, Variante, charger_correspondance, charger_questions, charger_variantes  # noqa: E402

RACINE = Path(__file__).resolve().parents[3]
RAPPORTS_DEFAUT = RACINE.parent / "mirai-apps-beta-private" / "private" / "rapports" / "campagne"
PHASES = ("harnais", "mcp")
NUITS_AVANT_ARRET = 3


# ─── La fenêtre de nuit ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fenetre:
    debut: heure
    fin: heure

    @property
    def a_cheval(self) -> bool:
        return self.fin <= self.debut

    def contient(self, t: datetime) -> bool:
        h = t.time()
        return (h >= self.debut or h < self.fin) if self.a_cheval else (self.debut <= h < self.fin)

    def nuit_de(self, t: datetime) -> date:
        """La date du soir où la nuit a commencé (02 h 00 le 2 appartient à la nuit du 1er)."""
        return t.date() - timedelta(days=1) if self.a_cheval and t.time() < self.fin else t.date()

    def attente_s(self, t: datetime) -> float:
        """Le temps jusqu'à l'ouverture (0 si ouverte)."""
        if self.contient(t):
            return 0.0
        ouverture = datetime.combine(t.date(), self.debut, tzinfo=t.tzinfo)
        if ouverture <= t:
            ouverture += timedelta(days=1)
        return (ouverture - t).total_seconds()


_HEURE = r"(\d{1,2})(?:[h:](\d{2})?)?"


def lire_fenetre(texte: str) -> Fenetre | None:
    """`21h-6h`, `21:00-06:00`, `21h30-5h45` ; `maintenant` : pas de fenêtre."""
    t = texte.strip().lower()
    if t == "maintenant":
        return None
    m = re.fullmatch(rf"{_HEURE}\s*-\s*{_HEURE}", t)
    if not m:
        raise Usage(f"--fenetre : « 21h-6h », « 21:00-06:00 » ou « maintenant » ({texte!r})")
    try:
        return Fenetre(heure(int(m[1]), int(m[2] or 0)), heure(int(m[3]), int(m[4] or 0)))
    except ValueError:
        raise Usage(f"--fenetre : heure invalide ({texte!r})") from None


# ─── Le journal de la nuit ───────────────────────────────────────────────────────────────────


def cle(phase: str, variante: str, question: str, nuit: str) -> str:
    return f"{phase}|{variante}|{question}|{nuit}"


class Journal:
    """`essais.jsonl` d'une nuit : une ligne par essai, relue à la reprise."""

    def __init__(self, dossier: Path):
        self.chemin = dossier / "essais.jsonl"
        self.lignes: list[dict] = []
        if self.chemin.exists():
            for ligne in self.chemin.read_text(encoding="utf-8").splitlines():
                try:
                    self.lignes.append(json.loads(ligne))
                except ValueError:
                    continue  # une ligne coupée par un arrêt brutal : l'essai se rejouera
        self._faits = {d["cle"] for d in self.lignes if d.get("statut") == "joue"}

    def fait(self, c: str) -> bool:
        return c in self._faits

    def ecrire(self, ligne: dict) -> None:
        self.lignes.append(ligne)
        if ligne.get("statut") == "joue":
            self._faits.add(ligne["cle"])
        with self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def total(self, champ: str) -> int:
        return sum(int(d.get(champ) or 0) for d in self.lignes)


# ─── La nuit ─────────────────────────────────────────────────────────────────────────────────


@dataclass
class Reglages:
    nuit: str
    dossier: Path
    phases: tuple[str, ...] = PHASES
    fenetre: Fenetre | None = None
    max_executer: int = 300
    max_appels_modele: int = 400
    juge_modele: str | None = None
    modele_agent: str = MODELE
    catalogue: int = 0
    liens_max: int = 3
    infos: dict = field(default_factory=dict)


class Campagne:
    def __init__(
        self,
        reglages: Reglages,
        cible: Cible,
        variantes: list[Variante],
        questions: list[Question],
        *,
        passerelle: Passerelle | None = None,
        maintenant: Callable[[], datetime] = datetime.now,
        dormir: Callable[[float], None] | None = None,
        dire: Callable[[str], None] = lambda s: print(s, flush=True),
    ):
        self.r, self.cible, self.variantes, self.questions = reglages, cible, variantes, questions
        self.passerelle = passerelle
        self.maintenant, self.dormir, self.dire = maintenant, dormir or cible.dormir, dire
        reglages.dossier.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(reglages.dossier)
        self.executer = self.journal.total("executer")
        self.juge = juges.JugeModele(passerelle, reglages.juge_modele) if passerelle and reglages.juge_modele else None
        self.agent = Agent(cible, passerelle, modele=reglages.modele_agent) if passerelle else None

    # La fenêtre

    def _attendre_ouverture(self) -> None:
        f = self.r.fenetre
        while f is not None and not f.contient(self.maintenant()):
            attente = f.attente_s(self.maintenant())
            self.dire(f"hors fenêtre : ouverture dans {int(attente // 60)} min")
            self.dormir(min(attente, 600.0))

    def _ouverte(self) -> bool:
        return self.r.fenetre is None or self.r.fenetre.contient(self.maintenant())

    def _ligne(self, phase: str, variante: str, question: str, **champs) -> dict:
        return {
            "cle": cle(phase, variante, question, self.r.nuit),
            "phase": phase,
            "variante": variante,
            "question": question,
            "nuit": self.r.nuit,
            "horodatage": self.maintenant().isoformat(timespec="seconds"),
            **champs,
        }

    def _modele_restant(self, besoin: int) -> bool:
        return self.passerelle is not None and self.passerelle.restants >= besoin

    def _juger_reponse(self, question: Question, reponse: str | None, regle: str | None) -> dict | None:
        if self.juge is None or question.refus_attendu or not reponse or question.reponse is None:
            return None
        if not self._modele_restant(1):
            return {"verdict": None, "erreur": "budget"}
        return self.juge.juger(question.texte, question.reponse, reponse, regle)

    def _juger_fidelite(self, question: Question, reponse: str | None, passages: list[str]) -> dict | None:
        """La réponse au regard des seuls passages reçus ; un refus attendu n'est pas jugé."""
        if self.juge is None or question.refus_attendu or not reponse:
            return None
        if not self._modele_restant(1):
            return {"verdict": None, "erreur": "budget"}
        return self.juge.fidelite(question.texte, passages, reponse)

    # Le chemin harnais

    def _lisibles(self) -> set[str] | None:
        """Les collections que le compte lit (`/api/v1/search/scopes`) : un passage d'une autre est un incident."""
        try:
            r = self.cible.appel("GET", "/api/v1/search/scopes", route="recherche")
        except httpx.TransportError:
            return None
        if r.status_code != 200:
            return None
        return {s.get("id") for s in r.json().get("scopes") or []}

    def harnais(self) -> str:
        lisibles = self._lisibles()
        for q in self.questions:  # question d'abord : s0, s1, s2 d'une même question se suivent
            for v in self.variantes:
                c = cle("harnais", v.nom, q.id, self.r.nuit)
                if self.journal.fait(c):
                    continue
                if self.executer >= self.r.max_executer:
                    return "budget-executer"
                if not self._ouverte():
                    return "fenetre"
                debut = self.cible.horloge()
                self.executer += 1
                try:
                    rep = self.cible.appel("POST", f"/api/v1/assistants/{v.assistant}/executer", route="assistants", json={"question": q.texte, "canal": "api", "rediger": True})
                except httpx.TransportError as e:
                    self.journal.ecrire(self._ligne("harnais", v.nom, q.id, statut="erreur", texte=q.texte, executer=1, erreur=type(e).__name__, attendu=q.attendu()))
                    continue
                ligne = self._ligne(
                    "harnais",
                    v.nom,
                    q.id,
                    texte=q.texte,
                    executer=1,
                    http=rep.status_code,
                    ms_client=int((self.cible.horloge() - debut) * 1000),
                    attendu=q.attendu(),
                    consignes_fiche=bool(v.consignes),
                )
                if rep.status_code != 200:
                    ligne.update(statut="erreur" if rep.status_code >= 500 or rep.status_code == 429 else "joue", erreur=rep.text[:300])
                    self.journal.ecrire(ligne)
                    continue
                corps = rep.json()
                verdicts = juges.juger_harnais(q, v, corps, lisibles)
                ligne.update(statut="joue", resultat=juges.resume_harnais(corps), verdicts=verdicts)
                ligne["liens"] = juges.verifier_liens(self.cible, juges.urls_citees_harnais(corps), max_liens=self.r.liens_max)
                avant = self.passerelle.appels if self.passerelle else 0
                try:
                    ligne["juge"] = self._juger_reponse(q, corps.get("reponse"), v.consignes.get(verdicts["consigne_obtenue"] or ""))
                    ligne["fidelite"] = self._juger_fidelite(q, corps.get("reponse"), [str(p.get("texte") or "") for p in corps.get("passages") or []])
                except BudgetEpuise:
                    ligne["juge"] = ligne.get("juge") or {"verdict": None, "erreur": "budget"}
                    ligne["fidelite"] = {"verdict": None, "erreur": "budget"}
                ligne["appels_modele"] = (self.passerelle.appels if self.passerelle else 0) - avant
                self.journal.ecrire(ligne)
                self.dire(
                    f"harnais {v.nom} {q.id} : {rep.status_code} consigne={verdicts['consigne_obtenue']} source@5={verdicts['source@5']} refus={verdicts['refus_obtenu']} {corps.get('duree_ms')} ms"
                )
                if verdicts["incidents"]:
                    self.cible.garde.incident(f"harnais {v.assistant} « {q.id} » : {', '.join(verdicts['incidents'][:3])}")
        return "complet"

    # Le chemin MCP

    def _essai_mcp(self, variante: str, ident: str, question: str, *, attendus: set[str], sources=(), temoin=None, q: Question | None = None, extra: dict | None = None) -> None:
        assert self.agent is not None and self.passerelle is not None
        avant = self.passerelle.appels
        ligne = self._ligne("mcp", variante, ident, texte=question, **(extra or {}))
        if q is not None:
            ligne["attendu"] = q.attendu()
        try:
            conv = self.agent.converser(question)
        except httpx.HTTPError as e:
            ligne.update(statut="erreur", erreur=type(e).__name__, appels_modele=self.passerelle.appels - avant)
            self.journal.ecrire(ligne)
            return
        verdicts = juges.juger_mcp(conv, attendus=attendus, sources=sources, temoin=temoin, canari=q.canari if q else None, refus_attendu=q.refus_attendu if q else False)
        ligne.update(statut="joue", conversation=conv, verdicts=verdicts)
        ligne["liens"] = juges.verifier_liens(self.cible, juges.liens_cites(conv.get("reponse")), max_liens=self.r.liens_max)
        if q is not None:
            try:
                ligne["juge"] = self._juger_reponse(q, conv.get("reponse"), None)
                ligne["fidelite"] = self._juger_fidelite(q, conv.get("reponse"), conv.get("contexte") or [])
            except BudgetEpuise:
                ligne["juge"] = ligne.get("juge") or {"verdict": None, "erreur": "budget"}
                ligne["fidelite"] = {"verdict": None, "erreur": "budget"}
        ligne["appels_modele"] = self.passerelle.appels - avant
        self.journal.ecrire(ligne)
        self.dire(f"mcp {variante} {ident} : outils={verdicts['outils']} bon_choix={verdicts['bon_choix']} source@5={verdicts['source@5']} {conv.get('duree_ms')} ms")
        if verdicts["incidents"]:
            self.cible.garde.incident(f"mcp « {ident} » : {', '.join(verdicts['incidents'][:3])}")

    def mcp(self) -> str:
        if self.agent is None:
            return "sans-passerelle"
        besoin = MAX_TOURS + (2 if self.juge else 0)  # le juge : référence et fidélité
        try:
            self.agent.outils()
        except ErreurMcp as e:
            self.dire(f"mcp indisponible : {e}")
            return "mcp-indisponible"
        essai = {v.assistant for v in self.variantes}
        for q in self.questions:
            if self.journal.fait(cle("mcp", "agent", q.id, self.r.nuit)):
                continue
            if not self._modele_restant(besoin):
                return "budget-modele"
            if not self._ouverte():
                return "fenetre"
            try:
                self._essai_mcp("agent", q.id, q.texte, attendus=(essai | set(q.sources)) if q.sources else set(), sources=q.sources, q=q)
            except BudgetEpuise:
                return "budget-modele"
        if self.r.catalogue > 0:
            return self._catalogue(besoin + 1)
        return "complet"

    def _catalogue(self, besoin: int) -> str:
        """Pour chaque collection lisible (hors essai), un passage tiré par la recherche, une question écrite par le modèle."""
        assert self.agent is not None
        r = self.cible.appel("GET", "/api/v1/search/scopes", route="recherche")
        if r.status_code != 200:
            return "catalogue-indisponible"
        scopes = sorted((s for s in r.json().get("scopes") or [] if not str(s.get("id", "")).startswith(PREFIXE)), key=lambda s: s["id"])[: self.r.catalogue]
        for s in scopes:
            if self.journal.fait(cle("mcp", "catalogue", s["id"], self.r.nuit)):
                continue
            if not self._modele_restant(besoin):
                return "budget-modele"
            if not self._ouverte():
                return "fenetre"
            rr = self.cible.appel("GET", "/api/v1/search", route="recherche", params={"q": s.get("title") or s["id"], "scope": s["id"], "limit": 3})
            resultats = (rr.json().get("results") or []) if rr.status_code == 200 else []
            touche = next(((res, h) for res in resultats for h in res.get("hits") or [] if h.get("snippet") and (h.get("url") or res.get("url"))), None)
            if touche is None:
                self.journal.ecrire(self._ligne("mcp", "catalogue", s["id"], statut="joue", http=rr.status_code, sans_passage=True))
                continue
            res, hit = touche
            try:
                question = self.agent.ecrire_question(hit["snippet"])
                if not question:
                    self.journal.ecrire(self._ligne("mcp", "catalogue", s["id"], statut="joue", sans_question=True, appels_modele=1))
                    continue
                self._essai_mcp(
                    "catalogue",
                    s["id"],
                    question,
                    attendus={s["id"]},
                    temoin=juges.chemin(hit.get("url") or res.get("url")),
                    extra={"temoin": juges.chemin(hit.get("url") or res.get("url"))},
                )
            except BudgetEpuise:
                return "budget-modele"
        return "complet"

    # La nuit entière

    def jouer(self) -> dict:
        execution: dict = {"debut": self.maintenant().isoformat(timespec="seconds"), "phases": {}, "arret": None}
        try:
            self._attendre_ouverture()
            for phase in self.r.phases:
                execution["phases"][phase] = getattr(self, phase)()
        except Arret as e:
            execution["arret"] = {"motif": e.motif, "detail": e.detail, "immediat": e.immediat}
            self.dire(f"ARRÊT ({e.motif}) : {e.detail}")
        finally:
            execution.update(
                fin=self.maintenant().isoformat(timespec="seconds"),
                executer=self.executer,
                appels_modele=self.journal.total("appels_modele"),
                reconnexions=self.cible.reconnexions,
                renouvellements=self.cible.renouvellements,
                appels=self.cible.compteurs,
                cadences={k: s.par_minute for k, s in self.cible.seaux.items()},
            )
            ecrire_etat(self.r, execution)
        return execution


def ecrire_etat(r: Reglages, execution: dict) -> None:
    chemin = r.dossier / "etat.json"
    etat: dict[str, Any]
    try:
        etat = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        etat = {"nuit": r.nuit, "executions": []}
    etat.update(
        reglages={
            "phases": list(r.phases),
            "fenetre": f"{r.fenetre.debut:%H:%M}-{r.fenetre.fin:%H:%M}" if r.fenetre else "maintenant",
            "max_executer": r.max_executer,
            "max_appels_modele": r.max_appels_modele,
            "juge_modele": r.juge_modele,
            "modele_agent": r.modele_agent,
            "catalogue": r.catalogue,
        },
        **r.infos,
    )
    etat["executions"].append(execution)
    chemin.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")


def campagne_arretee(racine: Path, nuit: str) -> str | None:
    """Le motif, si les trois nuits précédentes se sont arrêtées pareil (sinon None)."""
    motifs = []
    for d in sorted((p for p in racine.iterdir() if p.is_dir() and p.name < nuit), reverse=True)[:NUITS_AVANT_ARRET]:
        try:
            executions = json.loads((d / "etat.json").read_text(encoding="utf-8")).get("executions") or []
        except (OSError, ValueError):
            return None
        motifs.append(((executions[-1] if executions else {}).get("arret") or {}).get("motif"))
    if len(motifs) == NUITS_AVANT_ARRET and motifs[0] and len(set(motifs)) == 1:
        return motifs[0]
    return None


def dossier_rapports(valeur: str | None) -> Path:
    """La racine des rapports : jamais dans le dépôt."""
    racine = Path(valeur).expanduser() if valeur else RAPPORTS_DEFAUT
    racine = racine.resolve()
    if racine == RACINE or RACINE in racine.parents:
        raise Usage(f"les rapports ne s'écrivent jamais dans le dépôt : {racine}")
    return racine


def main(
    argv: list[str] | None = None, *, fabrique: Callable[[argparse.Namespace], tuple[Cible, Passerelle | None]] | None = None, maintenant: Callable[[], datetime] = datetime.now
) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.campagne.run", description="La campagne de nuit des chemins de recherche.")
    p.add_argument("--cible", default=os.environ.get("CAMPAGNE_CIBLE", ""), help="origine de Mes collections (défaut : CAMPAGNE_CIBLE)")
    p.add_argument("--jeu", type=Path, default=JEU_DEFAUT, help="dossier des fiches s*.yaml et de questions.yaml")
    p.add_argument("--correspondance", help="JSON alias → identifiant (défaut : CAMPAGNE_CORRESPONDANCE)")
    p.add_argument("--phases", default=",".join(PHASES), help="harnais, mcp, ou les deux (ordre respecté)")
    p.add_argument("--fenetre", default="21h-6h", help="« 21h-6h » (défaut) ou « maintenant »")
    p.add_argument("--nuit", help="la nuit (AAAA-MM-JJ) ; défaut : le soir où la fenêtre s'est ouverte")
    p.add_argument("--max-executer", type=int, default=300)
    p.add_argument("--max-appels-modele", type=int, default=400)
    p.add_argument("--juge-modele", help="modèle du juge (sans : juges déterministes seulement)")
    p.add_argument("--modele-agent", default=MODELE, help=f"modèle de l'agent MCP (défaut : {MODELE})")
    p.add_argument("--catalogue", type=int, default=0, help="collections du catalogue réel à essayer par le MCP (0 : aucune)")
    p.add_argument("--cadence-assistants", type=float, default=20.0, help="appels par minute à executer et /mcp (≤ 20)")
    p.add_argument("--rapports", default=os.environ.get("CAMPAGNE_RAPPORTS", ""), help="racine des rapports (défaut : CAMPAGNE_RAPPORTS)")
    p.add_argument("--forcer", action="store_true", help="démarrer même si la campagne est arrêtée (trois nuits du même échec)")
    a = p.parse_args(argv)
    try:
        phases = tuple(x.strip() for x in a.phases.split(",") if x.strip())
        if not phases or any(x not in PHASES for x in phases):
            raise Usage(f"--phases parmi {', '.join(PHASES)}")
        if not 0 < a.cadence_assistants <= 20:
            raise Usage("--cadence-assistants entre 0 et 20 par minute (quota partagé de 30)")
        fenetre = lire_fenetre(a.fenetre)
        racine = dossier_rapports(a.rapports or None)
        correspondance = charger_correspondance(a.correspondance)
        variantes = charger_variantes(a.jeu, correspondance)
        questions = charger_questions(a.jeu / "questions.yaml", correspondance, variantes)
        nuit = a.nuit or (fenetre.nuit_de(maintenant()) if fenetre else maintenant().date()).isoformat()
        if racine.exists() and not a.forcer and (motif := campagne_arretee(racine, nuit)):
            print(f"campagne arrêtée : les {NUITS_AVANT_ARRET} dernières nuits se sont arrêtées sur « {motif} » (--forcer après correction)", file=sys.stderr)
            return 4
        a.cadences = {"assistants": a.cadence_assistants}
        cible, passerelle = (fabrique or _fabrique)(a)
        if passerelle is None and ("mcp" in phases or a.juge_modele):
            raise Usage("la phase mcp et le juge-modèle demandent la passerelle (CAMPAGNE_GATEWAY_URL, CAMPAGNE_GATEWAY_TOKEN)")
        dossier = racine / nuit
        dossier.mkdir(parents=True, exist_ok=True)
        r = Reglages(
            nuit=nuit,
            dossier=dossier,
            phases=phases,
            fenetre=fenetre,
            max_executer=a.max_executer,
            max_appels_modele=a.max_appels_modele,
            juge_modele=a.juge_modele,
            modele_agent=a.modele_agent,
            catalogue=a.catalogue,
            infos={"jeu": a.jeu.name, "questions": len(questions), "variantes": {v.nom: {"assistant": v.assistant, "empreinte": v.empreinte} for v in variantes}},
        )
        if passerelle is not None:
            passerelle.deja = Journal(dossier).total("appels_modele")
        execution = Campagne(r, cible, variantes, questions, passerelle=passerelle, maintenant=maintenant).jouer()
    except (Usage, CorpusInvalide) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2
    synthese, _ = rapport.ecrire(dossier)
    print(f"rapport : {synthese}")
    return 3 if execution.get("arret") else 0


def _fabrique(a: argparse.Namespace) -> tuple[Cible, Passerelle | None]:
    base = origine(a.cible)
    sso = os.environ.get("CAMPAGNE_SSO_HOST", "").strip()
    manquantes = [n for n in ("CAMPAGNE_SSO_HOST", "KC_TEST_IN_USERNAME", "KC_TEST_IN_PASSWORD") if not os.environ.get(n, "").strip()]
    if manquantes:  # avant d'attendre la fenêtre : une nuit ne doit pas échouer à 21 h sur un réglage
        raise Usage(f"variables requises : {', '.join(manquantes)}")
    cible = Cible(base, connexion_navigateur(base, sso, compte="KC_TEST_IN"), cadences=a.cadences)
    besoin = "mcp" in a.phases or a.juge_modele
    passerelle = Passerelle.depuis_env(max_appels=a.max_appels_modele) if besoin else None
    return cible, passerelle


if __name__ == "__main__":
    sys.exit(main())
