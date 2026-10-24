"""Marquer « scan » des documents Résana déjà indexés avant le repérage des scans (#145).

Les scans de plusieurs pages importés avant le correctif d'OpenRAG (mycollections#151) passent pour
indexés : un seul passage, fait de marqueurs de page. Mes collections ne le sait pas (qualité
`inconnue`). Ce script pose, pour une liste d'identifiants dans l'index, `scan: true` et la qualité
que l'indexeur a constatée en les relisant :

- `sans_texte` : toujours illisibles (pas d'OCR). « Ré-indexer les documents incomplets » les
  reprendra quand l'OCR sera là ;
- `complet` : relus par OCR (la relecture par l'agent openrag a réussi).

Sans `--ecrire`, il ne fait que dire ce qu'il changerait. La fiche est relue juste avant l'écriture :
à ne pas lancer pendant un import de la même collection.

Dans le pod du backend (le script n'est pas dans l'image) : copier le script et la liste, puis
lancer d'abord sans `--ecrire` :

    kubectl cp scripts/marquer_scans.py <pod>:/tmp/marquer_scans.py
    kubectl cp <liste des file_id> <pod>:/tmp/scans.txt
    kubectl exec <pod> -- env PYTHONPATH=/app python /tmp/marquer_scans.py <collection> /tmp/scans.txt --etat sans_texte
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # lancé comme un fichier : la racine de `myrag` n'est pas sur le chemin
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ETATS = ("sans_texte", "complet")


def marquer(documents: dict[str, dict], identifiants: set[str], etat: str) -> list[str]:
    """Pose `scan` et la qualité sur les documents dont l'identifiant dans l'index est listé. Rend
    les identifiants Résana touchés. Pur : la fiche est modifiée sur place, rien n'est écrit."""
    touches = []
    for ident, fiche in documents.items():
        if fiche.get("file_id") in identifiants:
            fiche["scan"] = True
            fiche["qualite"] = {"etat": etat}
            if etat == "complet":
                fiche.pop("erreur", None)
            touches.append(ident)
    return touches


async def principal(collection: str, identifiants: set[str], etat: str, ecrire: bool) -> int:
    from app.services.collection_store import get_source_config, update_collection

    cfg = await get_source_config(collection)
    documents = dict(cfg.get("documents") or {})
    touches = marquer(documents, identifiants, etat)
    absents = len(identifiants) - len(touches)
    print(f"{collection} : {len(touches)} document(s) marqué(s) scan / {etat} ; {absents} identifiant(s) sans document correspondant.")
    if ecrire and touches:
        cfg["documents"] = documents
        await update_collection(collection, {"source_config_json": json.dumps(cfg)})
        print("Écrit.")
    elif touches:
        print("Rien n'est écrit (ajouter --ecrire).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("collection")
    p.add_argument("fichier", help="un file_id par ligne")
    p.add_argument("--etat", choices=ETATS, default="sans_texte")
    p.add_argument("--ecrire", action="store_true")
    a = p.parse_args()
    lignes = Path(a.fichier).read_text()
    identifiants = {ligne.strip() for ligne in lignes.splitlines() if ligne.strip()}
    return asyncio.run(principal(a.collection, identifiants, a.etat, a.ecrire))


if __name__ == "__main__":
    raise SystemExit(main())
