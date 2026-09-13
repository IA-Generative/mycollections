"""Les connecteurs d'amorces, par nom du catalogue. Chaque connecteur est
`async importer(collection, entree, **contexte) -> bilan chiffré`."""

from __future__ import annotations

from app.services.amorces import baac, justice_administrative, natinf, rne, sdis, ssmsi

CONNECTEURS = {
    "natinfo": natinf.importer,
    "ssmsi-delinquance": ssmsi.importer,
    "justice-administrative": justice_administrative.importer,
    "rne-elus": rne.importer,
    "sdis-interventions": sdis.importer,
    "baac": baac.importer,
}
