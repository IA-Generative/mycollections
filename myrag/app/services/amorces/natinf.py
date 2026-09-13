"""Codes NATINF — la liste officielle (ministère de la Justice, data.gouv.fr) énumère,
l'API natinfo.app enrichit (peines encourues, articles), quand une clé le permet.

La liste complète de natinfo.app exige une clé d'API ; sa fiche unitaire est ouverte
mais limitée à 120 appels par heure sans clé. D'où ce partage : l'énumération vient de
la nomenclature publiée, l'enrichissement de l'API, borné par `enrichir_max` et par
NATINFO_API_KEY.
"""

from __future__ import annotations

import os

import httpx

from app.services.amorces import reseau
from app.services.amorces.ingestion import Document
from app.services.amorces.tabulaire import colonne, lire_csv

PAR_DOCUMENT = 200
NUMERO = ("Numéro NATINF", "Numero NATINF", "numero_natinf")
QUALIFICATION = ("Qualification de l'infraction", "qualification_infraction")
NATURE = ("Nature de l'infraction", "nature_infraction")


def numero(l: dict) -> str:
    return colonne(l, *NUMERO).strip()


def _fiche(l: dict, enrichi: dict | None) -> str:
    lignes = [f"## NATINF {numero(l)} — {colonne(l, *QUALIFICATION)}", "",
              f"- Nature : {colonne(l, *NATURE)}",
              f"- Définie par : {colonne(l, 'Définie par', 'definie_par')}",
              f"- Réprimée par : {colonne(l, 'Réprimée par', 'reprimee_par')}"]
    if enrichi:
        for p in enrichi.get("peines_principales") or []:
            lignes.append(f"- Peine principale : {p.get('display_description') or p.get('template_label', '')}")
        for p in enrichi.get("peines_complementaires") or []:
            lignes.append(f"- Peine complémentaire : {p.get('display_description') or p.get('template_label', '')}")
        if enrichi.get("obsolete_date"):
            lignes.append(f"- Obsolète depuis : {enrichi['obsolete_date']}")
    return "\n".join(lignes)


def documents_depuis(lignes: list[dict], enrichis: dict[str, dict] | None = None) -> tuple[list[Document], dict]:
    enrichis = enrichis or {}
    lignes = [l for l in lignes if numero(l).isdigit()]
    lignes.sort(key=lambda l: int(numero(l)))
    docs = []
    for i in range(0, len(lignes), PAR_DOCUMENT):
        lot = lignes[i:i + PAR_DOCUMENT]
        premier, dernier = numero(lot[0]), numero(lot[-1])
        texte = "\n\n".join([f"# Nomenclature NATINF — codes {premier} à {dernier}", "Source : ministère de la Justice (data.gouv.fr), enrichie par natinfo.app."] +
                            [_fiche(l, enrichis.get(numero(l))) for l in lot])
        docs.append(Document(nom=f"natinf-{int(premier):05d}-{int(dernier):05d}.md", texte=texte))
    return docs, {"codes": len(lignes), "enrichis": len(enrichis), "documents": len(docs)}


async def enrichir(numeros: list[str], base_url: str, maximum: int) -> dict[str, dict]:
    """Lit les fiches unitaires de natinfo.app, par lots de 50, en respectant la limite de débit."""
    cle = os.environ.get("NATINFO_API_KEY", "")
    entetes = {"X-API-Key": cle} if cle else {}
    resultats: dict[str, dict] = {}
    numeros = numeros[: max(0, maximum)]
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(numeros), 50):
            lot = numeros[i:i + 50]
            r = await client.post(f"{base_url.rstrip('/')}/api/natinfs/batch/", json={"numeros": lot}, headers=entetes)
            if r.status_code == 429:
                break  # la limite de débit : on garde ce qu'on a, le prochain import complètera
            r.raise_for_status()
            for fiche in r.json().get("results", []):
                resultats[str(fiche.get("numero_natinf") or fiche.get("id"))] = fiche
    return resultats


async def importer(collection: str, entree: dict) -> dict:
    from app.services.amorces.ingestion import ingerer
    p = entree.get("parametres", {})
    lignes = lire_csv(await reseau.telecharger(p["url_liste"]))
    numeros = [numero(l) for l in lignes]
    enrichis = {}
    if p.get("enrichir_max", 0) > 0:
        try:
            enrichis = await enrichir([n for n in numeros if n], p.get("url_api", "https://natinfo.app"), int(p["enrichir_max"]))
        except httpx.HTTPError:
            enrichis = {}
    docs, couverture = documents_depuis(lignes, enrichis)
    bilan = await ingerer(collection, docs, strategie="section", max_documents=p.get("max_documents"))
    return {**bilan, "couverture": couverture, "lignes_importees": couverture["codes"]}
