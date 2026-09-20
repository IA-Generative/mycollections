"""Consulter le corpus d'une collection : la liste de ses documents, puis le texte de l'un d'eux.

La vérité du corpus est dans OpenRAG, pas dans la table `source_files` : une collection
importée par script (un code entier depuis Légifrance) n'a aucun fichier chez MyRAG.

Deux contraintes mesurées sur l'OpenRAG de la bêta, qui dictent la forme de ce module :
- `GET /partition/<p>` rend TOUS les fichiers d'un coup — 4,6 Mo pour les 3 585 entrées du
  CESEDA. On ne relaie jamais cette liste au navigateur : on cherche et on pagine ici, et
  on garde la liste une minute en mémoire pour ne pas la redemander à chaque page.
- `GET /partition/<p>/file/<id>` rend les métadonnées du fichier — vecteur d'embedding
  compris — et des LIENS vers ses morceaux. Le texte se relit morceau par morceau. On ne
  rend ni le vecteur, ni les chemins internes du serveur.
"""

from __future__ import annotations

import re
import time
import unicodedata

PAR_PAGE_DEFAUT = 50
PAR_PAGE_MAX = 200
MORCEAUX_MAX = 60  # au-delà, le document est rendu tronqué — et le dit
DUREE_CACHE = 60.0

_cache: dict[str, tuple[float, list[dict]]] = {}


def plier(s: str) -> str:
    """Minuscules sans accents : « Séjour » se trouve en tapant « sejour »."""
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def _cle_naturelle(s: str) -> list:
    """« partie 2/10 » avant « partie 10/10 » : les nombres se comparent en nombres."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", plier(s))]


def resumer_fichier(f: dict) -> dict:
    """Ce qu'on montre d'un fichier d'OpenRAG — rien d'interne (ni `source`, ni condensé, ni vecteur)."""
    fichier = str(f.get("original_filename") or f.get("filename") or "")
    url = str(f.get("url") or "")
    return {
        "file_id": str(f.get("file_id") or ""),
        "titre": str(f.get("title") or fichier or f.get("file_id") or "Document"),
        "fichier": fichier,
        "type": str(f.get("mimetype") or ""),
        "taille": str(f.get("file_size") or ""),
        "url_source": url if url.startswith(("https://", "http://")) else "",
    }


def chercher_et_paginer(fichiers: list[dict], q: str = "", page: int = 1, par_page: int = PAR_PAGE_DEFAUT) -> dict:
    """Résume, filtre (tous les mots de `q`, sans accents ni casse), trie, et rend UNE page."""
    par_page = max(1, min(int(par_page or PAR_PAGE_DEFAUT), PAR_PAGE_MAX))
    docs = [d for d in (resumer_fichier(f) for f in fichiers if isinstance(f, dict)) if d["file_id"]]
    mots = plier(q).split()
    if mots:
        docs = [d for d in docs if all(m in plier(f"{d['titre']} {d['fichier']} {d['file_id']}") for m in mots)]
    docs.sort(key=lambda d: (_cle_naturelle(d["titre"]), d["file_id"]))
    total = len(docs)
    pages = max(1, -(-total // par_page))
    page = max(1, min(int(page or 1), pages))
    debut = (page - 1) * par_page
    return {"total": total, "page": page, "pages": pages, "par_page": par_page, "documents": docs[debut:debut + par_page]}


def identifiants_des_morceaux(detail: dict) -> list[str]:
    """Les identifiants de morceaux d'un fichier, dans l'ordre, lus dans ses liens `/extract/<id>`."""
    ids: list[str] = []
    for d in (detail or {}).get("documents") or []:
        m = re.search(r"/extract/([^/?#]+)", str((d or {}).get("link") or "")) if isinstance(d, dict) else None
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


async def fichiers_de(client, partition: str) -> list[dict]:
    """La liste des fichiers d'une partition, gardée une minute : feuilleter ne la redemande pas."""
    vu = _cache.get(partition)
    if vu and time.monotonic() - vu[0] < DUREE_CACHE:
        return vu[1]
    fichiers = await client.list_files(partition)
    _cache[partition] = (time.monotonic(), fichiers)
    return fichiers


def oublier(partition: str | None = None) -> None:
    """Vide le cache (tests, ou après une ingestion)."""
    _cache.clear() if partition is None else _cache.pop(partition, None)
