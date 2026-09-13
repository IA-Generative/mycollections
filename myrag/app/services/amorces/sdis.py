"""Interventions des services d'incendie et de secours — un document par département,
années en lignes, grandes familles d'interventions en colonnes."""

from __future__ import annotations

from collections import defaultdict

from app.services.amorces import reseau
from app.services.amorces.ingestion import Document
from app.services.amorces.tabulaire import colonne, entier, fmt, lire_csv

FAMILLES = ("Incendies", "Secours à personne", "Accidents de circulation", "Risques technologiques",
            "Opérations diverses", "Total interventions")


def _val(l: dict, nom: str) -> int:
    # Les en-têtes cp1252 mal relus ont parfois « ŕ » pour « à » : on tolère les deux.
    return entier(colonne(l, nom, nom.replace("à", "ŕ")))


def documents_depuis(par_annee: dict[str, list[dict]]) -> tuple[list[Document], dict]:
    par_dep: dict[str, dict[str, dict]] = defaultdict(dict)
    noms: dict[str, str] = {}
    for annee, lignes in par_annee.items():
        for l in lignes:
            num = colonne(l, "Numéro", "Numero").strip()
            dep = colonne(l, "Département", "Departement").strip()
            if not dep:
                continue
            cle = num or dep
            noms[cle] = dep
            par_dep[cle][annee] = {f: _val(l, f) for f in FAMILLES}
            par_dep[cle][annee]["region"] = colonne(l, "Région", "Region")
    docs = []
    for cle in sorted(par_dep, key=lambda k: (len(k), k)):
        nom = noms[cle]
        md = [f"# Interventions des sapeurs-pompiers — {nom} (SIS {cle})", "",
              "Source : DGSCGC, interventions réalisées par les services d'incendie et de secours (data.gouv.fr). Nombre d'interventions par famille et par année.", "",
              "| année | " + " | ".join(FAMILLES) + " |", "|" + "---|" * (len(FAMILLES) + 1)]
        for annee in sorted(par_dep[cle]):
            v = par_dep[cle][annee]
            md.append(f"| {annee} | " + " | ".join(fmt(v[f]) for f in FAMILLES) + " |")
        docs.append(Document(nom=f"sis-{cle}.md", texte="\n".join(md), metadonnees={"departement": nom}))
    annees = sorted(par_annee)
    return docs, {"departements": len(par_dep), "annees": [annees[0], annees[-1]] if annees else [],
                  "lignes_lues": sum(len(v) for v in par_annee.values())}


async def importer(collection: str, entree: dict) -> dict:
    from app.services.amorces.ingestion import ingerer
    p = entree.get("parametres", {})
    par_annee = {}
    for f in p["fichiers"]:
        par_annee[str(f["annee"])] = lire_csv(await reseau.telecharger(f["url"]))
    docs, couverture = documents_depuis(par_annee)
    bilan = await ingerer(collection, docs, max_documents=p.get("max_documents"))
    return {**bilan, "couverture": couverture, "lignes_importees": couverture["lignes_lues"]}
