"""Jurisprudence administrative (TA, CAA, CE) — depuis les ZIP mensuels XML
d'opendata.justice-administrative.fr, filtrée par mots-clés et par période, réimport
incrémental par mois. La couverture réelle (juridictions, dates, décisions lues et
retenues) est constatée à l'import et consignée dans la grille.

Adresses observées le 2026-09-13 : /DTA/AAAA/MM/TA_AAAAMM.zip, /DCA/AAAA/MM/CAA_AAAAMM.zip,
/DCE/AAAA/MM/CE_AAAAMM.zip. Un ZIP mensuel des TA pèse ~60 Mio, celui des CAA ~9 Mio.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from datetime import date
from xml.etree import ElementTree

from app.services.amorces import reseau
from app.services.amorces.ingestion import Document

BASE = "https://opendata.justice-administrative.fr"
FONDS = {"DTA": "TA", "DCA": "CAA", "DCE": "CE"}
_BALISES = re.compile(r"</?p>|<[^>]+>")


def url_du_mois(fonds: str, annee: int, mois: int) -> str:
    return f"{BASE}/{fonds}/{annee:04d}/{mois:02d}/{FONDS[fonds]}_{annee:04d}{mois:02d}.zip"


def mois_entre(depuis: str, jusqua: date | None = None) -> list[tuple[int, int]]:
    """Les mois de `depuis` (AAAA-MM) au mois précédent aujourd'hui, inclus."""
    a, m = (int(x) for x in depuis.split("-")[:2])
    fin = jusqua or date.today()
    fin_a, fin_m = fin.year, fin.month
    mois = []
    while (a, m) < (fin_a, fin_m):
        mois.append((a, m))
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return mois


def _normaliser(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def decision_depuis_xml(xml: bytes) -> dict | None:
    try:
        racine = ElementTree.fromstring(xml.lstrip(b"\xef\xbb\xbf"))
    except ElementTree.ParseError:
        return None
    dossier = racine.find("Dossier")
    texte_el = racine.find("Decision/Texte_Integral")
    if dossier is None or texte_el is None:
        return None
    brut = "".join(texte_el.itertext()) if len(texte_el) else (texte_el.text or "")
    # Le corps est une suite de <p> ; chaque ligne est un paragraphe.
    corps = "\n".join(s.strip() for s in _BALISES.sub("\n", brut).splitlines() if s.strip())
    champ = lambda n: (dossier.findtext(n) or "").strip()  # noqa: E731
    return {
        "code_juridiction": champ("Code_Juridiction"), "juridiction": champ("Nom_Juridiction"),
        "numero": champ("Numero_Dossier"), "date": champ("Date_Lecture"), "ecli": champ("Numero_ECLI"),
        "type": champ("Type_Decision"), "recours": champ("Type_Recours"), "publication": champ("Code_Publication"),
        "solution": champ("Solution"), "formation": champ("Formation_Jugement"), "texte": corps,
    }


def retenue(d: dict, mots_cles: list[str], codes_publication: list[str] | None) -> bool:
    if codes_publication and d.get("publication") and d["publication"] not in codes_publication:
        return False
    t = _normaliser(d["texte"])
    return any(_normaliser(m) in t for m in mots_cles)


def document_depuis(d: dict, fonds: str) -> Document:
    md = [f"# {d['juridiction'] or d['code_juridiction']} — {d['type'] or 'décision'} n° {d['numero']} du {d['date']}", "",
          f"- Juridiction : {d['juridiction']} ({d['code_juridiction']})", f"- Numéro : {d['numero']}", f"- Date de lecture : {d['date']}"]
    for k, lib in (("ecli", "ECLI"), ("recours", "Type de recours"), ("solution", "Solution"), ("formation", "Formation"), ("publication", "Code de publication")):
        if d.get(k):
            md.append(f"- {lib} : {d[k]}")
    md += ["", "Source : opendata.justice-administrative.fr, décision pseudonymisée à la source.", "", "## Texte intégral", "", d["texte"]]
    return Document(nom=f"{FONDS[fonds]}-{d['numero']}-{d['date']}.md", texte="\n".join(md),
                    metadonnees={"juridiction": d["code_juridiction"], "date": d["date"]})


def decisions_du_zip(octets: bytes) -> list[dict]:
    decisions = []
    with zipfile.ZipFile(io.BytesIO(octets)) as z:
        for nom in z.namelist():
            if not nom.lower().endswith(".xml"):
                continue
            d = decision_depuis_xml(z.read(nom))
            if d:
                decisions.append(d)
    return decisions


async def importer(collection: str, entree: dict, *, deja_importes: list[str] | None = None) -> dict:
    """Importe les mois manquants, dans l'ordre, jusqu'à `max_mois_par_run`."""
    from app.services.amorces.ingestion import ingerer
    p = entree.get("parametres", {})
    fonds = p.get("fonds", ["DCA", "DTA"])
    mots = p.get("mots_cles", ["CESEDA"])
    codes = p.get("codes_publication")
    faits = set(deja_importes or [])
    a_faire = [(f, a, m) for (a, m) in mois_entre(p.get("depuis", "2024-01")) for f in fonds if f"{f}-{a:04d}{m:02d}" not in faits]
    a_faire = a_faire[: int(p.get("max_mois_par_run", 2))]
    docs, mois_faits, lues, retenues = [], [], 0, 0
    juridictions, dates = set(), []
    for f, a, m in a_faire:
        try:
            octets = await reseau.telecharger(url_du_mois(f, a, m))
        except Exception as e:  # noqa: BLE001 — un mois absent (pas encore publié) n'arrête pas le reste
            if "404" in str(e):
                continue
            raise
        decisions = decisions_du_zip(octets)
        lues += len(decisions)
        gardees = [d for d in decisions if retenue(d, mots, codes)][: int(p.get("max_par_mois", 400))]
        retenues += len(gardees)
        for d in gardees:
            docs.append(document_depuis(d, f))
            juridictions.add(d["code_juridiction"])
            if d["date"]:
                dates.append(d["date"])
        mois_faits.append(f"{f}-{a:04d}{m:02d}")
    bilan = await ingerer(collection, docs, strategie="section", max_documents=p.get("max_documents"))
    couverture = {"fonds": fonds, "mots_cles": mots, "mois_importes": sorted(faits | set(mois_faits)),
                  "juridictions": sorted(juridictions), "dates": [min(dates), max(dates)] if dates else [],
                  "decisions_lues": lues, "decisions_retenues": retenues,
                  "reste_a_importer": max(0, len([1 for (a, m) in mois_entre(p.get("depuis", "2024-01")) for f in fonds]) - len(faits | set(mois_faits)))}
    return {**bilan, "couverture": couverture, "lignes_importees": retenues, "mois_importes": mois_faits}
