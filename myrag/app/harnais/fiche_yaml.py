"""La fiche d'un assistant en YAML : un fichier par assistant, qu'une équipe écrit, relit et
versionne, et qu'un testeur exporte ou importe depuis l'écran.

Le YAML n'est qu'une écriture de la fiche : ce qui fait foi reste le contrat (`contrat.py`), son
texte canonique et son empreinte. `charger` lit par `yaml.safe_load` seulement (aucune balise
`!!python/…`, aucun alias), refuse une clef en double, puis valide le contrat ; une erreur dit le
champ et la règle, en français. `ecrire` rend un texte stable (ordre des champs fixe), et
`charger(ecrire(f))` a la même empreinte que `f`.

`reference` (dérivée des jeux de questions) et `publication` (réglée à l'écran Publication) ne
viennent jamais d'un fichier : présentes, elles sont ignorées avec un avertissement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml
from pydantic import ValidationError
from pydantic_core import ErrorDetails
from yaml.constructor import ConstructorError

from app.harnais.contrat import CONTRAT_VERSION, IDENT_RELAIS, FicheAssistant, canonique, empreinte

#: Un fichier de fiche ne dépasse pas cette taille (en octets, UTF-8).
TAILLE_MAX = 64 * 1024
#: Champs de la fiche qu'un fichier ne fixe pas, et pourquoi.
IGNORES = {
    "reference": "« reference » est calculée à partir des jeux de questions : la valeur du fichier est ignorée",
    "publication": "« publication » se règle dans l'écran Publication : la valeur du fichier est ignorée",
}


@dataclass
class ErreurChamp:
    champ: str
    message: str

    def __str__(self) -> str:
        return f"{self.champ} : {self.message}" if self.champ else self.message


class FicheYamlInvalide(ValueError):
    """Le fichier n'est pas une fiche valide. `erreurs` : une par champ fautif."""

    def __init__(self, erreurs: list[ErreurChamp]):
        self.erreurs = erreurs
        super().__init__("; ".join(str(e) for e in erreurs))


@dataclass
class Lecture:
    fiche: FicheAssistant
    avertissements: list[str] = field(default_factory=list)


# ─── Lire ────────────────────────────────────────────────────────────────────────────────────


class _Refus(yaml.MarkedYAMLError):
    """Un refus de `_Chargeur`, au message déjà en français."""


class _Chargeur(yaml.SafeLoader):
    """`SafeLoader`, sans alias (`*nom`, qui démultiplie un contenu) ni clef en double (la
    seconde écraserait la première sans rien dire : un relecteur ne verrait pas ce qui vaut)."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            ev = self.peek_event()
            raise _Refus(None, None, "les alias YAML (*nom) ne sont pas acceptés", ev.start_mark)
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        vues = set()
        for cle, _ in node.value:
            k = self.construct_object(cle, deep=deep)
            if isinstance(k, str | int | float | bool) and k in vues:
                raise _Refus(None, None, f"la clef « {k} » apparaît deux fois", cle.start_mark)
            vues.add(k)
        return super().construct_mapping(node, deep=deep)


def _lieu(e: yaml.YAMLError) -> str:
    mark = getattr(e, "problem_mark", None)
    return f"ligne {mark.line + 1}, colonne {mark.column + 1}" if mark is not None else "fichier"


def _message_yaml(e: yaml.YAMLError) -> str:
    probleme = getattr(e, "problem", None) or str(e)
    if isinstance(e, _Refus):
        return probleme
    if isinstance(e, ConstructorError) and "could not determine a constructor" in probleme:
        return "balise YAML refusée (seules les données simples sont lues : textes, nombres, listes, objets)"
    return f"YAML illisible : {probleme}"


def _chemin(loc: tuple, donnees: object) -> str:
    """`('consignes', 1, 'chercher', 0, 'source')` → `consignes[2] (accord-bilateral) › chercher[1] › source`
    (rangs comptés à partir de 1, comme on lit le fichier ; l'identifiant quand il y en a un)."""
    morceaux: list[str] = []
    courant = donnees
    for p in loc:
        if isinstance(p, int):
            ident = courant[p].get("id") if isinstance(courant, list) and p < len(courant) and isinstance(courant[p], dict) else None
            base = morceaux.pop() if morceaux else ""
            morceaux.append(f"{base}[{p + 1}]" + (f" ({ident})" if isinstance(ident, str) and ident else ""))
        else:
            morceaux.append(str(p))
        if isinstance(courant, dict):
            courant = courant.get(p) if isinstance(p, str) else None
        elif isinstance(courant, list) and isinstance(p, int) and p < len(courant):
            courant = courant[p]
        else:
            courant = None
    return " › ".join(morceaux)


def _message(err: ErrorDetails) -> str:
    t, ctx = err.get("type", ""), err.get("ctx") or {}
    if t == "missing":
        return "champ obligatoire absent"
    if t == "extra_forbidden":
        return "champ inconnu du contrat (vérifiez l'orthographe)"
    if t == "string_type":
        return "doit être un texte (entre guillemets si la valeur ressemble à un nombre, une date, yes ou no)"
    if t == "string_pattern_mismatch":
        if ctx.get("pattern") == IDENT_RELAIS:
            return "nom de relais invalide : minuscules, chiffres et « _ », commençant par une lettre (ex. article_trouve)"
        return "identifiant invalide : 3 à 64 caractères, minuscules, chiffres, « . », « _ » ou « - »"
    if t == "literal_error":
        return f"valeur non admise : attendu {ctx.get('expected', '')}".replace(" or ", " ou ").rstrip()
    if t == "string_too_short":
        return "ne peut pas être vide" if ctx.get("min_length") == 1 else f"trop court : au moins {ctx.get('min_length')} caractères"
    if t == "string_too_long":
        return f"trop long : au plus {ctx.get('max_length')} caractères"
    if t == "too_short":
        return f"au moins {ctx.get('min_length')} élément(s)"
    if t == "too_long":
        return f"trop d'éléments : au plus {ctx.get('max_length')}"
    if t in ("greater_than_equal", "greater_than"):
        return f"doit être supérieur{' ou égal' if t.endswith('equal') else ''} à {ctx.get('ge', ctx.get('gt'))}"
    if t in ("less_than_equal", "less_than"):
        return f"doit être inférieur{' ou égal' if t.endswith('equal') else ''} à {ctx.get('le', ctx.get('lt'))}"
    if t.startswith("float") or t.startswith("int"):
        return "doit être un nombre" if t.startswith("float") else "doit être un nombre entier"
    if t.startswith("bool"):
        return "doit valoir true ou false"
    if t == "list_type":
        return "doit être une liste"
    if t in ("dict_type", "model_type", "model_attributes_type"):
        return "doit être un objet (clef: valeur)"
    msg = str(err.get("msg", "valeur invalide"))
    return msg.removeprefix("Value error, ")


def lire(texte: str | bytes) -> Lecture:
    """La fiche que décrit ce YAML, et les avertissements (champs ignorés). `FicheYamlInvalide` sinon."""
    if isinstance(texte, bytes):
        if len(texte) > TAILLE_MAX:
            raise FicheYamlInvalide([ErreurChamp("fichier", f"trop gros : {TAILLE_MAX // 1024} Kio au plus")])
        try:
            texte = texte.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise FicheYamlInvalide([ErreurChamp("fichier", "doit être encodé en UTF-8")]) from None
    if len(texte.encode("utf-8")) > TAILLE_MAX:
        raise FicheYamlInvalide([ErreurChamp("fichier", f"trop gros : {TAILLE_MAX // 1024} Kio au plus")])
    try:
        donnees = yaml.load(texte, Loader=_Chargeur)  # noqa: S506 — _Chargeur dérive de SafeLoader
    except yaml.YAMLError as e:
        raise FicheYamlInvalide([ErreurChamp(_lieu(e), _message_yaml(e))]) from None
    if not isinstance(donnees, dict):
        raise FicheYamlInvalide([ErreurChamp("fichier", "doit décrire un objet (assistant:, titre:, sources:…)")])
    avertissements = [msg for cle, msg in IGNORES.items() if donnees.pop(cle, None) is not None]
    try:
        fiche = FicheAssistant.model_validate(donnees)
    except ValidationError as e:
        raise FicheYamlInvalide([ErreurChamp(_chemin(err["loc"], donnees) or "fiche", _message(err)) for err in e.errors(include_url=False)]) from None
    return Lecture(fiche=fiche, avertissements=avertissements)


def charger(texte: str | bytes) -> FicheAssistant:
    """La fiche que décrit ce YAML (sans les avertissements : voir `lire`)."""
    return lire(texte).fiche


# ─── Écrire ──────────────────────────────────────────────────────────────────────────────────


class _Compact(dict):
    """Un objet écrit sur une ligne : `{id: ceseda, type: collection, …}`."""


class _ListeCompacte(list):
    """Une liste écrite sur une ligne : `["un exemple", "un autre"]`."""


class _Guillemets(str):
    pass


class _Ecrivain(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        # Une liste sous une clef s'indente (« sources:\n  - … ») : la forme qu'on écrit à la main.
        return super().increase_indent(flow, False)


def _texte(d: yaml.SafeDumper, s: str):
    return d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None)


_Ecrivain.add_representer(str, _texte)
_Ecrivain.add_representer(_Guillemets, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", str(s), style='"'))
_Ecrivain.add_representer(_Compact, lambda d, m: d.represent_mapping("tag:yaml.org,2002:map", m.items(), flow_style=True))
_Ecrivain.add_representer(_ListeCompacte, lambda d, li: d.represent_sequence("tag:yaml.org,2002:seq", li, flow_style=True))
#: Au-delà, des exemples s'écrivent un par ligne (une ligne par exemple, un diff lisible).
_LARGEUR_COMPACTE = 100


def _compact(d: dict) -> _Compact:
    return _Compact((k, v) for k, v in d.items() if v is not None)


def _exemples(exemples: list[str]):
    if sum(len(e) + 4 for e in exemples) <= _LARGEUR_COMPACTE and not any("\n" in e for e in exemples):
        return _ListeCompacte(_Guillemets(e) for e in exemples)
    return list(exemples)


def _consigne(c) -> dict:
    d: dict = {"id": c.id, "quand": c.quand}
    if c.exemples:
        d["exemples"] = _exemples(c.exemples)
    if c.chercher:
        d["chercher"] = [_compact({"source": e.source, "avec": e.avec}) for e in c.chercher]
    if c.repondre:
        d["repondre"] = c.repondre
    if c.gabarit:
        d["gabarit"] = c.gabarit
    return d


def ecrire(fiche: FicheAssistant, *, entete: list[str] | None = None) -> str:
    """Le YAML de la fiche. En tête, en commentaires : la version du contrat et l'empreinte (celle
    que prendra la version publiée), le résumé de `reference` s'il est connu, puis `entete`.

    Ordre : l'identité et les réglages d'abord (assistant, titre, rubrique, description,
    seuil_fiable, validation_requise), puis les sources et les consignes ; dans un objet, l'ordre
    du contrat. Les valeurs par défaut des champs facultatifs ne s'écrivent pas."""
    lignes = [f"# contrat: {CONTRAT_VERSION} · empreinte: sha256:{empreinte(canonique(fiche))}"]
    if fiche.reference is not None:
        lignes.append(f"# reference (calculée, ignorée à l'import) : {fiche.reference.questions} questions, {fiche.reference.fiables} fiables")
    lignes += [f"# {ligne}" for ligne in (entete or [])]
    d: dict = {"assistant": fiche.assistant, "titre": fiche.titre}
    if fiche.rubrique is not None:
        d["rubrique"] = fiche.rubrique
    if fiche.description:
        d["description"] = fiche.description
    d["seuil_fiable"] = fiche.seuil_fiable
    d["validation_requise"] = fiche.validation_requise
    d["sources"] = [_compact({"id": s.id, "type": s.type, "regime": s.regime, "rang": s.rang}) for s in fiche.sources]
    d["consignes"] = [_consigne(c) for c in fiche.consignes]
    corps = yaml.dump(d, Dumper=_Ecrivain, allow_unicode=True, sort_keys=False, width=10_000, indent=2, default_flow_style=False)
    return "\n".join(lignes) + "\n" + corps
