"""Délinquance enregistrée (SSMSI) — base départementale : un document par département,
un tableau par indicateur, années en colonnes."""

from __future__ import annotations

from collections import defaultdict

from app.services.amorces import reseau
from app.services.amorces.ingestion import Document
from app.services.amorces.tabulaire import fmt, lire_csv, nombre


def documents_depuis(lignes: list[dict]) -> tuple[list[Document], dict]:
    par_dep: dict[str, dict[str, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    annees, indicateurs = set(), set()
    for l in lignes:
        dep, annee, ind = l.get("Code_departement", ""), l.get("annee", ""), l.get("indicateur", "")
        if not (dep and annee and ind):
            continue
        annees.add(annee); indicateurs.add(ind)
        par_dep[dep][ind][annee] = {
            "nombre": nombre(l.get("nombre")), "taux": nombre(l.get("taux_pour_mille")),
            "unite": l.get("unite_de_compte", ""), "pop": nombre(l.get("insee_pop")),
        }
    docs = []
    for dep in sorted(par_dep):
        lignes_md = [f"# Délinquance enregistrée par la police et la gendarmerie — département {dep}", ""]
        lignes_md.append("Source : SSMSI, base statistique départementale (data.gouv.fr). Nombre de faits ou de victimes enregistrés, et taux pour mille habitants (population INSEE).")
        for ind in sorted(par_dep[dep]):
            serie = par_dep[dep][ind]
            unite = next(iter(serie.values()))["unite"]
            lignes_md += ["", f"## {ind} (unité : {unite}) — département {dep}", "", "| année | nombre | taux pour 1 000 habitants |", "|---|---|---|"]
            for a in sorted(serie):
                lignes_md.append(f"| {a} | {fmt(serie[a]['nombre'])} | {fmt(serie[a]['taux'], 2) if serie[a]['taux'] is not None else '—'} |")
        docs.append(Document(nom=f"ssmsi-departement-{dep}.md", texte="\n".join(lignes_md), metadonnees={"departement": dep}))
    couverture = {"departements": len(par_dep), "annees": [min(annees), max(annees)] if annees else [],
                  "indicateurs": sorted(indicateurs), "lignes_lues": len(lignes)}
    return docs, couverture


async def importer(collection: str, entree: dict) -> dict:
    from app.services.amorces.ingestion import ingerer
    p = entree.get("parametres", {})
    octets = await reseau.telecharger(p["url_departemental"])
    docs, couverture = documents_depuis(lire_csv(octets))
    bilan = await ingerer(collection, docs, max_documents=p.get("max_documents"))
    return {**bilan, "couverture": couverture, "lignes_importees": couverture["lignes_lues"]}
