"""Accidents corporels de la circulation (BAAC) — un document par département et par
année : accidents, tués, blessés, en/hors agglomération, et les communes les plus
touchées. Aucune donnée d'usager individuelle n'est reprise."""

from __future__ import annotations

from collections import Counter, defaultdict

from app.services.amorces import reseau
from app.services.amorces.ingestion import Document
from app.services.amorces.tabulaire import colonne, fmt, lire_csv

GRAVITE = {"2": "tues", "3": "blesses_hospitalises", "4": "blesses_legers", "1": "indemnes"}


def documents_depuis(annee: str, caract: list[dict], usagers: list[dict], communes_max: int = 15) -> tuple[list[Document], dict]:
    grav_par_acc: dict[str, Counter] = defaultdict(Counter)
    for u in usagers:
        grav_par_acc[colonne(u, "Num_Acc")][GRAVITE.get(colonne(u, "grav").strip(), "autres")] += 1
    par_dep: dict[str, dict] = defaultdict(lambda: {"accidents": 0, "agglo": 0, "hors": 0, "tues": 0,
                                                    "blesses_hospitalises": 0, "blesses_legers": 0, "communes": Counter(), "mois": Counter()})
    for c in caract:
        dep = colonne(c, "dep").strip()
        if not dep:
            continue
        d = par_dep[dep]
        d["accidents"] += 1
        d["agglo" if colonne(c, "agg").strip() == "2" else "hors"] += 1
        d["communes"][colonne(c, "com").strip()] += 1
        d["mois"][colonne(c, "mois").strip().zfill(2)] += 1
        g = grav_par_acc.get(colonne(c, "Num_Acc"), Counter())
        for k in ("tues", "blesses_hospitalises", "blesses_legers"):
            d[k] += g[k]
    docs = []
    for dep in sorted(par_dep):
        d = par_dep[dep]
        md = [f"# Accidents corporels de la circulation — département {dep}, année {annee}", "",
              "Source : ONISR, bases BAAC (data.gouv.fr). Un accident corporel = au moins une victime. Aucune donnée individuelle.", "",
              f"- Accidents corporels : {fmt(d['accidents'])} (en agglomération : {fmt(d['agglo'])}, hors agglomération : {fmt(d['hors'])})",
              f"- Tués : {fmt(d['tues'])} · blessés hospitalisés : {fmt(d['blesses_hospitalises'])} · blessés légers : {fmt(d['blesses_legers'])}",
              "", f"## Communes les plus touchées en {annee} (code INSEE, nombre d'accidents)", ""]
        for com, n in d["communes"].most_common(communes_max):
            md.append(f"- {com} : {n}")
        md += ["", f"## Répartition par mois en {annee}", ""]
        for m in sorted(d["mois"]):
            md.append(f"- {annee}-{m} : {d['mois'][m]}")
        docs.append(Document(nom=f"baac-{annee}-departement-{dep}.md", texte="\n".join(md), metadonnees={"departement": dep, "annee": annee}))
    return docs, {"annee": annee, "departements": len(par_dep), "accidents": len(caract), "usagers": len(usagers)}


async def importer(collection: str, entree: dict) -> dict:
    from app.services.amorces.ingestion import ingerer
    p = entree.get("parametres", {})
    docs, couverture = [], {"annees": [], "accidents": 0, "departements": 0}
    for f in p["millesimes"]:
        caract = lire_csv(await reseau.telecharger(f["caracteristiques"]))
        usagers = lire_csv(await reseau.telecharger(f["usagers"])) if f.get("usagers") else []
        d, c = documents_depuis(str(f["annee"]), caract, usagers, p.get("communes_max", 15))
        docs += d
        couverture["annees"].append(str(f["annee"]))
        couverture["accidents"] += c["accidents"]
        couverture["departements"] = max(couverture["departements"], c["departements"])
    couverture["annees"] = [min(couverture["annees"]), max(couverture["annees"])] if couverture["annees"] else []
    bilan = await ingerer(collection, docs, max_documents=p.get("max_documents"))
    return {**bilan, "couverture": couverture, "lignes_importees": couverture["accidents"]}
