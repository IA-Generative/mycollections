"""La fiche d'un assistant en YAML, en ligne de commande (docs/assistants.md, « Le fichier YAML »).

    cd myrag
    uv run python -m scripts.fiche verifier ../docs/exemples/assistants/sejour-des-etrangers.yaml
    uv run python -m scripts.fiche exporter <id> --cible https://mycollections.fake-domain.name --jeton-env JETON [--sortie <id>.yaml]
    uv run python -m scripts.fiche appliquer <id>.yaml --cible https://mycollections.fake-domain.name --jeton-env JETON [--publier]

`verifier` ne touche pas le réseau : il valide le fichier contre le contrat et affiche l'empreinte
que prendra la version publiée. `exporter` et `appliquer` appellent `GET|PUT
/api/assistants/{id}/fiche.yaml` avec les droits de la personne dont le jeton (d'accès, Keycloak)
est lu dans la variable d'environnement nommée par `--jeton-env` — jamais passé en argument, où
l'historique du terminal et la liste des processus le verraient. `--publier` fige ensuite le
brouillon en version (une seule si rien n'a changé).

Codes de sortie : 0 réussi ; 1 fichier invalide ou refusé ; 2 usage ou service injoignable.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

if __package__ in (None, ""):  # lancé comme un fichier : la racine de `myrag` n'est pas sur le chemin
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harnais import fiche_yaml  # noqa: E402
from app.harnais.contrat import canonique, empreinte  # noqa: E402

DELAI_S = 30.0


class Usage(Exception):
    pass


def _cible(url: str) -> str:
    """L'origine du service : https, sauf sur le poste (le jeton ne circule pas en clair)."""
    u = urlsplit(url.rstrip("/"))
    if u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")):
        return url.rstrip("/")
    raise Usage(f"--cible doit être une adresse https (http seulement vers localhost) : {url}")


def _entetes(variable: str | None) -> dict[str, str]:
    if not variable:
        return {}
    jeton = os.environ.get(variable, "").strip()
    if not jeton:
        raise Usage(f"la variable d'environnement {variable} est vide ou absente")
    return {"Authorization": f"Bearer {jeton}"}


def _refus(r: httpx.Response) -> str:
    try:
        detail = r.json().get("detail")
    except ValueError:
        detail = r.text[:500]
    if isinstance(detail, dict):
        lignes = [detail.get("message", "")] + [f"  - {e.get('champ')} : {e.get('message')}" for e in detail.get("erreurs", [])]
        detail = "\n".join(lignes)
    return f"refusé ({r.status_code}) : {detail}"


def verifier(chemin: Path) -> int:
    try:
        lecture = fiche_yaml.lire(chemin.read_bytes())
    except fiche_yaml.FicheYamlInvalide as e:
        print(f"{chemin} : fiche invalide", file=sys.stderr)
        for err in e.erreurs:
            print(f"  - {err}", file=sys.stderr)
        return 1
    for a in lecture.avertissements:
        print(f"avertissement : {a}", file=sys.stderr)
    print(f"{chemin} : fiche valide · assistant {lecture.fiche.assistant} · empreinte sha256:{empreinte(canonique(lecture.fiche))}")
    return 0


def exporter(ident: str, cible: str, entetes: dict, sortie: Path | None, client: httpx.Client) -> int:
    r = client.get(f"{cible}/api/assistants/{quote(ident, safe='')}/fiche.yaml", headers=entetes)
    if r.status_code != 200:
        print(_refus(r), file=sys.stderr)
        return 1
    if sortie is None:
        sys.stdout.write(r.text)
    else:
        sortie.write_text(r.text, encoding="utf-8")
        print(f"{sortie} : écrit", file=sys.stderr)
    return 0


def appliquer(chemin: Path, cible: str, entetes: dict, publier: bool, client: httpx.Client) -> int:
    contenu = chemin.read_bytes()
    try:
        fiche = fiche_yaml.charger(contenu)  # refuser ici ce que le service refuserait, sans l'appeler
    except fiche_yaml.FicheYamlInvalide:
        return verifier(chemin)
    url = f"{cible}/api/assistants/{quote(fiche.assistant, safe='')}"
    r = client.put(f"{url}/fiche.yaml", content=contenu, headers={**entetes, "Content-Type": "text/yaml; charset=utf-8"})
    if r.status_code != 200:
        print(_refus(r), file=sys.stderr)
        return 1
    corps = r.json()
    for a in corps.get("avertissements", []):
        print(f"avertissement : {a}", file=sys.stderr)
    print(f"{fiche.assistant} : brouillon enregistré · empreinte sha256:{corps.get('empreinte')}")
    if publier:
        p = client.post(f"{url}/publier", headers=entetes)
        if p.status_code != 200:
            print(_refus(p), file=sys.stderr)
            return 1
        v = p.json()
        print(f"{fiche.assistant} : version {v['version']}{' (nouvelle)' if v.get('nouvelle') else ' (inchangée)'} · empreinte sha256:{v['empreinte']}")
    return 0


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.fiche", description="La fiche d'un assistant en YAML.")
    sous = p.add_subparsers(dest="commande", required=True)
    v = sous.add_parser("verifier", help="valide un fichier (hors réseau) et affiche son empreinte")
    v.add_argument("fichier", type=Path)
    for nom, aide in (("exporter", "télécharge le brouillon d'un assistant"), ("appliquer", "remplace le brouillon par un fichier")):
        s = sous.add_parser(nom, help=aide)
        s.add_argument("ident" if nom == "exporter" else "fichier", type=str if nom == "exporter" else Path)
        s.add_argument("--cible", required=True, help="origine de Mes collections (https)")
        s.add_argument("--jeton-env", help="nom de la variable d'environnement qui porte le jeton d'accès")
        if nom == "exporter":
            s.add_argument("--sortie", type=Path, help="fichier à écrire (sinon : la sortie standard)")
        else:
            s.add_argument("--publier", action="store_true", help="publie ensuite le brouillon en version")
    a = p.parse_args(argv)
    if a.commande == "verifier":
        return verifier(a.fichier)
    try:
        cible, entetes = _cible(a.cible), _entetes(a.jeton_env)
        with httpx.Client(timeout=DELAI_S, transport=transport) as client:
            if a.commande == "exporter":
                return exporter(a.ident, cible, entetes, a.sortie, client)
            return appliquer(a.fichier, cible, entetes, a.publier, client)
    except Usage as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2
    except httpx.HTTPError as e:
        print(f"erreur : service injoignable ({type(e).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
