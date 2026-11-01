"""Les assistants d'essai de la campagne et son jeu de questions.

Les fiches d'essai (`tests/campagne/<jeu>/s*.yaml`) et les questions sont publiques et inventées :
leurs sources s'écrivent par ALIAS (`guide`, `faq`, `jurisprudence`…), jamais par l'identifiant
d'une collection réelle. Un fichier de correspondance privé, hors dépôt, donne l'identifiant de
chaque alias sur la cible : `CAMPAGNE_CORRESPONDANCE`, un objet JSON `{"alias": "identifiant"}`.

Seuls les assistants préfixés `e2e-camp-` se manipulent ici : un autre identifiant est refusé
avant tout appel. Aucune collection n'est créée.

    cd myrag
    uv run python -m scripts.campagne.corpus resoudre                   # hors réseau : valide, empreintes
    uv run --with playwright python -m scripts.campagne.corpus verifier  --cible https://mycollections.fake-domain.name
    uv run --with playwright python -m scripts.campagne.corpus appliquer --cible https://mycollections.fake-domain.name [--publier]

`verifier` et `appliquer` se connectent avec le compte d'administration de test
(`KC_TEST_ADMIN_USERNAME` / `_PASSWORD`). `appliquer` est idempotent : une fiche déjà conforme
n'est pas réécrite, et sa publication ne crée pas de nouvelle version.

Codes de sortie : 0 réussi ; 1 fiche invalide, refusée ou différente ; 2 usage ou cible injoignable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml

if __package__ in (None, ""):  # lancé comme un fichier : la racine de `myrag` n'est pas sur le chemin
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.harnais import fiche_yaml  # noqa: E402
from app.harnais.contrat import QUAND_TOUJOURS, FicheAssistant, canonique, empreinte  # noqa: E402

PREFIXE = "e2e-camp-"
CATEGORIES = ("declenche", "voisine", "pieces", "hors_champ", "injection")
CONTRAINTES = ("accord_avant_code", "pieces_listees", "decisions_citees")
#: La réponse attendue quand rien, dans les documents, ne répond.
NE_REPOND_PAS = "ne répond pas"
JEU_DEFAUT = Path(__file__).resolve().parents[2] / "tests" / "campagne" / "sejour-des-etrangers"


class CorpusInvalide(ValueError):
    pass


# ─── La correspondance des alias ─────────────────────────────────────────────────────────────


def charger_correspondance(chemin: str | Path | None = None) -> dict[str, str]:
    """`{alias: identifiant}` du fichier privé (`CAMPAGNE_CORRESPONDANCE` par défaut)."""
    chemin = chemin or os.environ.get("CAMPAGNE_CORRESPONDANCE", "").strip()
    if not chemin:
        raise CorpusInvalide("CAMPAGNE_CORRESPONDANCE est requis : le fichier JSON privé qui donne l'identifiant de chaque alias")
    try:
        d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CorpusInvalide(f"correspondance illisible ({type(e).__name__}) : {chemin}") from None
    if not isinstance(d, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in d.items()):
        raise CorpusInvalide('la correspondance doit être un objet JSON {"alias": "identifiant"}')
    return d


def _resoudre(alias: str, correspondance: dict[str, str], lieu: str) -> str:
    if alias not in correspondance:
        raise CorpusInvalide(f"{lieu} : alias « {alias} » absent de la correspondance")
    return correspondance[alias]


# ─── Les variantes d'un assistant d'essai ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Variante:
    nom: str  # « s0 », le nom du fichier
    fiche: FicheAssistant  # sources résolues
    alias: dict[str, str] = field(default_factory=dict)  # identifiant → alias, pour le rapport

    @property
    def assistant(self) -> str:
        return self.fiche.assistant

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.fiche.sources)

    @property
    def consignes(self) -> dict[str, str]:
        """Les consignes qu'un plan peut retenir (hors « toujours »), et leur règle `repondre`."""
        return {c.id: c.repondre for c in self.fiche.consignes if c.quand != QUAND_TOUJOURS}

    @property
    def empreinte(self) -> str:
        return empreinte(canonique(self.fiche))

    def texte(self) -> str:
        return fiche_yaml.ecrire(self.fiche, entete=["fiche d'essai de la campagne (scripts/campagne), sources résolues"])


def resoudre_fiche(texte: str, correspondance: dict[str, str], nom: str = "fiche") -> Variante:
    """La fiche d'essai, alias remplacés par les identifiants de la cible, validée par le contrat."""
    try:
        d = yaml.safe_load(texte)
    except yaml.YAMLError as e:
        raise CorpusInvalide(f"{nom} : YAML illisible ({e.__class__.__name__})") from None
    if not isinstance(d, dict):
        raise CorpusInvalide(f"{nom} : la fiche doit être un objet")
    if not str(d.get("assistant", "")).startswith(PREFIXE):
        raise CorpusInvalide(f"{nom} : seul un assistant préfixé « {PREFIXE} » se manipule ici ({d.get('assistant')!r})")
    inverse: dict[str, str] = {}
    for i, s in enumerate(d.get("sources") or []):
        ident = _resoudre(str(s.get("id")), correspondance, f"{nom}, sources[{i}]")
        inverse[ident] = s["id"]
        s["id"] = ident
    for c in d.get("consignes") or []:
        for e in c.get("chercher") or []:
            e["source"] = _resoudre(str(e.get("source")), correspondance, f"{nom}, consigne {c.get('id')}")
    try:
        fiche = fiche_yaml.charger(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))
    except fiche_yaml.FicheYamlInvalide as e:
        raise CorpusInvalide(f"{nom} : fiche invalide — " + " ; ".join(str(x) for x in e.erreurs)) from None
    return Variante(nom=nom, fiche=fiche, alias=inverse)


def charger_variantes(dossier: Path, correspondance: dict[str, str]) -> list[Variante]:
    """Les fiches `s*.yaml` du jeu, dans l'ordre de leur nom (s0, s1, s2…)."""
    fichiers = sorted(dossier.glob("s*.yaml"))
    if not fichiers:
        raise CorpusInvalide(f"aucune fiche s*.yaml dans {dossier}")
    variantes = [resoudre_fiche(f.read_text(encoding="utf-8"), correspondance, f.stem) for f in fichiers]
    if len({v.assistant for v in variantes}) != len(variantes):
        raise CorpusInvalide("deux fiches décrivent le même assistant")
    return variantes


# ─── Le jeu de questions ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Question:
    id: str
    texte: str
    categorie: str
    #: Les sources (identifiants résolus) dont un passage répond ; vide : hors champ.
    sources: tuple[str, ...] = ()
    #: La consigne qu'une fiche qui la porte doit retenir ; None : aucune.
    consigne: str | None = None
    #: La réponse de référence ; None : « ne répond pas » attendu.
    reponse: str | None = None
    contraintes: tuple[str, ...] = ()
    #: Injection : un mot que la réponse ne doit jamais contenir.
    canari: str | None = None

    @property
    def refus_attendu(self) -> bool:
        return self.reponse is None

    def consigne_pour(self, variante: Variante) -> str | None:
        """La consigne attendue sur CETTE variante : aucune si sa fiche ne la porte pas."""
        return self.consigne if self.consigne in variante.consignes else None

    def attendu(self) -> dict:
        return {
            "categorie": self.categorie,
            "sources": list(self.sources),
            "consigne": self.consigne,
            "refus": self.refus_attendu,
            "contraintes": list(self.contraintes),
        }


def charger_questions(chemin: Path, correspondance: dict[str, str], variantes: list[Variante] | None = None) -> list[Question]:
    try:
        d = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise CorpusInvalide(f"{chemin} illisible ({type(e).__name__})") from None
    lignes = (d or {}).get("questions") if isinstance(d, dict) else None
    if not isinstance(lignes, list) or not lignes:
        raise CorpusInvalide(f"{chemin} : une liste « questions: » est attendue")
    connues = set().union(*(v.consignes for v in variantes)) if variantes else None
    questions, vus = [], set()
    for i, q in enumerate(lignes):
        lieu = f"questions[{i}] ({q.get('id') if isinstance(q, dict) else '?'})"
        if not isinstance(q, dict) or not q.get("id") or not str(q.get("texte", "")).strip():
            raise CorpusInvalide(f"{lieu} : id et texte sont requis")
        if q["id"] in vus:
            raise CorpusInvalide(f"{lieu} : identifiant en double")
        vus.add(q["id"])
        if q.get("categorie") not in CATEGORIES:
            raise CorpusInvalide(f"{lieu} : categorie parmi {', '.join(CATEGORIES)}")
        consigne = q.get("consigne", "aucune")
        consigne = None if consigne in (None, "aucune") else str(consigne)
        if consigne is not None and connues is not None and consigne not in connues:
            raise CorpusInvalide(f"{lieu} : consigne « {consigne} » portée par aucune fiche")
        contraintes = tuple(q.get("contraintes") or ())
        if any(c not in CONTRAINTES for c in contraintes):
            raise CorpusInvalide(f"{lieu} : contraintes parmi {', '.join(CONTRAINTES)}")
        reponse = str(q.get("reponse") or "").strip()
        if not reponse:
            raise CorpusInvalide(f"{lieu} : reponse requise (une réponse de référence, ou « {NE_REPOND_PAS} »)")
        questions.append(
            Question(
                id=str(q["id"]),
                texte=str(q["texte"]).strip(),
                categorie=q["categorie"],
                sources=tuple(_resoudre(str(a), correspondance, lieu) for a in (q.get("sources") or ())),
                consigne=consigne,
                reponse=None if reponse.casefold() == NE_REPOND_PAS else reponse,
                contraintes=contraintes,
                canari=q.get("canari"),
            )
        )
    return questions


# ─── La cible : vérifier, appliquer ──────────────────────────────────────────────────────────


def etat(cible, variante: Variante) -> str:
    """`conforme`, `different`, `absent`, ou `illisible (<code>)` : le brouillon de la cible comparé à la fiche."""
    r = cible.appel("GET", f"/api/assistants/{quote(variante.assistant, safe='')}/fiche.yaml", route="admin")
    if r.status_code == 404:
        return "absent"
    if r.status_code != 200:
        return f"illisible ({r.status_code})"
    try:
        actuelle = fiche_yaml.charger(r.text)
    except fiche_yaml.FicheYamlInvalide:
        return "illisible (fiche)"
    return "conforme" if empreinte(canonique(actuelle)) == variante.empreinte else "different"


def appliquer(cible, variante: Variante, *, publier: bool = False) -> dict:
    """Remplace le brouillon s'il diffère, puis publie si demandé (sans nouvelle version si rien n'a changé)."""
    if not variante.assistant.startswith(PREFIXE):  # garde-fou, resoudre_fiche l'a déjà refusé
        raise CorpusInvalide(f"seul un assistant préfixé « {PREFIXE} » se manipule ici")
    url = f"/api/assistants/{quote(variante.assistant, safe='')}"
    avant = etat(cible, variante)
    sortie: dict = {"assistant": variante.assistant, "avant": avant, "ecrit": False, "publie": None}
    if avant != "conforme":
        r = cible.appel("PUT", f"{url}/fiche.yaml", route="admin", content=variante.texte().encode(), headers={"Content-Type": "text/yaml; charset=utf-8"})
        if r.status_code != 200:
            sortie["erreur"] = f"PUT {r.status_code} : {r.text[:300]}"
            return sortie
        sortie["ecrit"] = True
    if publier:
        p = cible.appel("POST", f"{url}/publier", route="admin")
        if p.status_code != 200:
            sortie["erreur"] = f"publier {p.status_code} : {p.text[:300]}"
            return sortie
        v = p.json()
        sortie["publie"] = {"version": v.get("version"), "nouvelle": bool(v.get("nouvelle"))}
    return sortie


def main(argv: list[str] | None = None, *, fabrique_cible=None) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.campagne.corpus", description="Les assistants d'essai de la campagne.")
    p.add_argument("commande", choices=("resoudre", "verifier", "appliquer"))
    p.add_argument("--jeu", type=Path, default=JEU_DEFAUT, help="dossier des fiches s*.yaml et de questions.yaml")
    p.add_argument("--correspondance", help="fichier JSON alias → identifiant (défaut : CAMPAGNE_CORRESPONDANCE)")
    p.add_argument("--cible", default=os.environ.get("CAMPAGNE_CIBLE", ""), help="origine de Mes collections (défaut : CAMPAGNE_CIBLE)")
    p.add_argument("--publier", action="store_true", help="publie ensuite chaque fiche (appliquer)")
    a = p.parse_args(argv)
    try:
        correspondance = charger_correspondance(a.correspondance)
        variantes = charger_variantes(a.jeu, correspondance)
        questions = charger_questions(a.jeu / "questions.yaml", correspondance, variantes)
    except CorpusInvalide as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 1
    if a.commande == "resoudre":
        for v in variantes:
            print(f"{v.nom} : {v.assistant} · {len(v.sources)} sources · {len(v.consignes)} consignes · empreinte sha256:{v.empreinte}")
        print(f"questions : {len(questions)}")
        return 0

    from scripts.campagne import cible as module_cible

    try:
        if fabrique_cible is not None:
            c = fabrique_cible(a.cible)
        else:
            base = module_cible.origine(a.cible)
            sso = os.environ.get("CAMPAGNE_SSO_HOST", "").strip()
            c = module_cible.Cible(base, module_cible.connexion_navigateur(base, sso, compte="KC_TEST_ADMIN"))
        code = 0
        for v in variantes:
            if a.commande == "verifier":
                e = etat(c, v)
                print(f"{v.nom} : {v.assistant} · {e}")
                code = code or (0 if e == "conforme" else 1)
            else:
                s = appliquer(c, v, publier=a.publier)
                print(f"{v.nom} : {json.dumps(s, ensure_ascii=False)}")
                code = code or (1 if "erreur" in s else 0)
        return code
    except module_cible.Usage as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2
    except module_cible.Arret as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2
    except httpx.HTTPError as e:
        print(f"erreur : cible injoignable ({type(e).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
