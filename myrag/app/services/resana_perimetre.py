"""Le périmètre d'une collection Résana : quels sous-dossiers elle indexe, ce qu'elle couvre du
dossier choisi, et quand dire à l'importeur qu'une mise à jour serait utile (docs/resana.md).

Fonctions pures : la route lit Résana et la configuration, ce module décide.

Le périmètre s'écrit en **exclusions** : le dossier racine est indexé, sauf les sous-dossiers
exclus (et tout ce qu'ils contiennent). Un sous-dossier créé plus tard dans Résana entre donc de
lui-même dans l'index, sauf s'il est rangé sous un dossier exclu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

from app.services.connectors.resana import DocumentResana, Dossier

#: Au-delà, l'index d'une collection Résana « semble ancien ».
FRAICHEUR_JOURS = 7


def enfants_par_parent(dossiers: list[Dossier]) -> dict[str | None, list[Dossier]]:
    par: dict[str | None, list[Dossier]] = {}
    for d in dossiers:
        par.setdefault(d.parent_id, []).append(d)
    return par


def sous_arbre(racine: str, dossiers: list[Dossier]) -> list[Dossier]:
    """Les dossiers sous `racine` (elle exceptée), dans l'ordre d'un parcours en profondeur."""
    par = enfants_par_parent(dossiers)
    rendu: list[Dossier] = []
    vus: set[str] = {racine}

    def descendre(ident: str) -> None:
        for d in sorted(par.get(ident, []), key=lambda d: d.titre.lower()):
            if d.id in vus:
                continue  # une boucle dans les données ne bloque rien
            vus.add(d.id)
            rendu.append(d)
            descendre(d.id)

    descendre(racine)
    return rendu


def exclus_effectifs(exclus: list[str], dossiers: list[Dossier]) -> set[str]:
    """Les dossiers exclus et tout ce qu'ils contiennent."""
    par = enfants_par_parent(dossiers)
    rendu: set[str] = set()
    pile = list(exclus)
    while pile:
        ident = pile.pop()
        if ident in rendu:
            continue
        rendu.add(ident)
        pile.extend(d.id for d in par.get(ident, []))
    return rendu


def dans_le_perimetre(docs: list[DocumentResana], exclus: set[str]) -> list[DocumentResana]:
    return [d for d in docs if not d.dossier_id or d.dossier_id not in exclus]


@dataclass(frozen=True)
class Noeud:
    id: str
    titre: str
    parent_id: str | None
    profondeur: int
    #: Documents rangés directement dans ce dossier, et dans tout son sous-arbre.
    documents: int
    documents_total: int
    taille_approx_mo: float | None

    def vers_dict(self) -> dict:
        return {
            "id": self.id,
            "titre": self.titre,
            "parent_id": self.parent_id,
            "profondeur": self.profondeur,
            "documents": self.documents,
            "documents_total": self.documents_total,
            "taille_approx_mo": self.taille_approx_mo,
        }


def inventaire(racine: str, dossiers: list[Dossier], docs: list[DocumentResana]) -> tuple[int, list[Noeud]]:
    """(documents rangés directement à la racine, sous-dossiers avec leurs comptes)."""
    arbre = sous_arbre(racine, dossiers)
    connus = {d.id for d in arbre}
    directs: dict[str, int] = {}
    tailles: dict[str, float] = {}
    a_la_racine = 0
    for doc in docs:
        cle = doc.dossier_id if doc.dossier_id in connus else None
        if cle is None:
            a_la_racine += 1
            continue
        directs[cle] = directs.get(cle, 0) + 1
        if doc.taille_approx_mo is not None:
            tailles[cle] = tailles.get(cle, 0.0) + doc.taille_approx_mo
    par = enfants_par_parent(arbre)
    profondeurs: dict[str, int] = {}
    totaux: dict[str, int] = {}
    totaux_mo: dict[str, float] = {}

    def total(ident: str) -> tuple[int, float]:
        if ident not in totaux:
            totaux[ident], totaux_mo[ident] = directs.get(ident, 0), tailles.get(ident, 0.0)
            for e in par.get(ident, []):
                n, mo = total(e.id)
                totaux[ident] += n
                totaux_mo[ident] += mo
        return totaux[ident], totaux_mo[ident]

    for d in arbre:
        profondeurs[d.id] = 0 if d.parent_id == racine else profondeurs.get(d.parent_id or "", 0) + 1
    noeuds = []
    for d in arbre:
        n, mo = total(d.id)
        noeuds.append(Noeud(d.id, d.titre, d.parent_id, profondeurs[d.id], directs.get(d.id, 0), n, round(mo, 1) if mo else None))
    return a_la_racine, noeuds


def couverture(cfg: dict) -> dict:
    """Ce que l'index couvre du dossier choisi, lisible par l'écran et par les listes :
    `totale` si rien n'est exclu et que la dernière passe est allée au bout, sinon `partielle`
    avec ses raisons (`selection` : des sous-dossiers sont exclus ; `interrompue` : la dernière
    passe s'est arrêtée en route ; `a_faire` : rien n'est encore indexé)."""
    exclus = list((cfg.get("perimetre") or {}).get("exclus") or [])
    travail = cfg.get("travail") or {}
    indexes = len(cfg.get("documents") or {})
    raisons = []
    if exclus:
        raisons.append("selection")
    if travail.get("etat") in ("partiel", "echec", "interrompu") or (travail.get("etat") == "en_cours" and indexes):
        raisons.append("interrompue")
    if not cfg.get("last_sync_at") and not indexes:
        raisons.append("a_faire")
    return {
        "couverture": "partielle" if raisons else "totale",
        "raisons": raisons,
        "documents_indexes": indexes,
        "documents_perimetre": cfg.get("documents_perimetre"),
        "documents_disponibles": cfg.get("documents_disponibles"),
        "dossiers_exclus": len(exclus),
        "derniere_lecture": cfg.get("last_sync_at"),
    }


def _date(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def avis(collection: str, cfg: dict, *, est_importeur: bool, maintenant: datetime, seuil_jours: int = FRAICHEUR_JOURS, titre: str = "") -> dict | None:
    """L'invitation à mettre l'index à jour, glissée dans une réponse ou une recherche : seulement
    pour la personne qui peut synchroniser, et seulement quand c'est utile (index ancien, ou passe
    restée incomplète ou en échec). None sinon. Le message nomme la collection (`titre`) : une
    recherche sur deux collections Résana donne deux avis qu'on distingue. `action.url` est relatif
    à l'origine du front de Mes collections."""
    if not est_importeur:
        return None
    travail = cfg.get("travail") or {}
    if travail.get("etat") == "en_cours":
        return None
    nom = titre.strip() or collection
    action = {"libelle": "Mettre à jour", "url": f"/c/{quote(collection, safe='')}/upload?synchroniser=1"}
    if travail.get("etat") in ("partiel", "interrompu", "echec"):
        return {
            "collection": collection,
            "titre": nom,
            "code": "resana_incomplet",
            "message": f"L'index Résana de « {nom} » est incomplet : la dernière mise à jour n'est pas allée au bout. Souhaitez-vous la reprendre ?",
            "action": {**action, "libelle": "Reprendre"},
        }
    derniere = _date(cfg.get("last_sync_at"))
    if derniere is None:
        return None
    jours = (maintenant - derniere).days
    if jours < seuil_jours:
        return None
    return {
        "collection": collection,
        "titre": nom,
        "code": "resana_ancien",
        "message": f"L'index Résana de « {nom} » semble ancien (dernière lecture il y a {jours} jours). Souhaitez-vous le mettre à jour ?",
        "action": action,
        "jours": jours,
    }
