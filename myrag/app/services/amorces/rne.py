"""Répertoire national des élus — limité aux colonnes NON nominatives à l'import.

Ne sont lues que : département, commune (code et libellé), canton, mandat, sexe (pour
un comptage), dates de début de mandat et de fonction, libellé de fonction. Nom,
prénom, date de naissance, catégorie socio-professionnelle et nationalité ne quittent
jamais le lecteur CSV. Le document produit dit, par commune, QUAND le mandat et la
fonction ont commencé et COMBIEN d'élus siègent — jamais QUI.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from app.services.amorces import reseau
from app.services.amorces.ingestion import Document
from app.services.amorces.tabulaire import colonne, fmt, lire_csv

COLONNES_LUES = ("Code du département", "Libellé du département", "Code de la commune", "Libellé de la commune",
                 "Code du canton", "Libellé du canton", "Code sexe", "Date de début du mandat",
                 "Date de début de la fonction", "Libellé de la fonction")
COLONNES_INTERDITES = ("Nom de l'élu", "Prénom de l'élu", "Date de naissance",
                       "Code de la catégorie socio-professionnelle", "Libellé de la catégorie socio-professionnelle",
                       "Code nationalité")


def _epurer(l: dict) -> dict:
    return {k: v for k, v in l.items() if k in COLONNES_LUES}


def documents_depuis(fichiers: dict[str, list[dict]]) -> tuple[list[Document], dict]:
    """fichiers : mandat → lignes brutes. Les lignes sont épurées AVANT tout traitement."""
    par_dep: dict[str, dict] = defaultdict(lambda: {"nom": "", "mandats": defaultdict(Counter), "communes": {}})
    total = 0
    for mandat, lignes in fichiers.items():
        for brut in lignes:
            l = _epurer(brut)
            total += 1
            dep = colonne(l, "Code du département").strip()
            if not dep:
                continue
            d = par_dep[dep]
            d["nom"] = d["nom"] or colonne(l, "Libellé du département")
            d["mandats"][mandat][colonne(l, "Code sexe").strip() or "?"] += 1
            com = colonne(l, "Code de la commune").strip()
            if com:
                c = d["communes"].setdefault(com, {"libelle": colonne(l, "Libellé de la commune"), "conseillers": 0,
                                                   "maire_mandat": "", "maire_fonction": ""})
                if mandat == "maires":
                    c["maire_mandat"] = colonne(l, "Date de début du mandat")
                    c["maire_fonction"] = colonne(l, "Date de début de la fonction")
                elif mandat == "conseillers_municipaux":
                    c["conseillers"] += 1
    docs = []
    for dep in sorted(par_dep):
        d = par_dep[dep]
        md = [f"# Élus du département {dep} — {d['nom']} (répertoire national des élus)", "",
              "Source : ministère de l'Intérieur, RNE (data.gouv.fr). Import limité aux colonnes non nominatives : aucun nom, prénom, date de naissance ni profession.", "",
              "## Effectifs par mandat", ""]
        for mandat in sorted(d["mandats"]):
            c = d["mandats"][mandat]
            md.append(f"- {mandat.replace('_', ' ')} : {fmt(sum(c.values()))} (femmes : {fmt(c.get('F', 0))}, hommes : {fmt(c.get('M', 0))})")
        if d["communes"]:
            md += ["", "## Par commune : début du mandat et de la fonction du maire, conseillers municipaux", "",
                   "| code INSEE | commune | mandat du maire depuis | fonction de maire depuis | conseillers municipaux |", "|---|---|---|---|---|"]
            for com in sorted(d["communes"]):
                c = d["communes"][com]
                md.append(f"| {com} | {c['libelle']} | {c['maire_mandat'] or '—'} | {c['maire_fonction'] or '—'} | {c['conseillers'] or '—'} |")
        docs.append(Document(nom=f"rne-departement-{dep}.md", texte="\n".join(md), metadonnees={"departement": dep}))
    return docs, {"departements": len(par_dep), "mandats": sorted(fichiers), "lignes_lues": total,
                  "colonnes_lues": list(COLONNES_LUES), "colonnes_ecartees": list(COLONNES_INTERDITES)}


async def importer(collection: str, entree: dict) -> dict:
    from app.services.amorces.ingestion import ingerer
    p = entree.get("parametres", {})
    fichiers = {}
    for f in p["fichiers"]:
        fichiers[f["mandat"]] = lire_csv(await reseau.telecharger(f["url"]))
    docs, couverture = documents_depuis(fichiers)
    bilan = await ingerer(collection, docs, max_documents=p.get("max_documents"))
    return {**bilan, "couverture": couverture, "lignes_importees": couverture["lignes_lues"]}
