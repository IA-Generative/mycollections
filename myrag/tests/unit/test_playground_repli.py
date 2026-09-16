"""Le repli par recherche : quand le RAG du chat ne rend aucune source.

Mesuré sur l'amorce NATINF : « Quel est le libellé de l'infraction NATINF 7987 ? »
rend zéro source par le chat (le seuil de similarité écarte un identifiant nu),
alors que /search classe le bon morceau en premier. Le repli rejoue la question en
recherche, injecte les morceaux comme contexte, et rend de VRAIES sources.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.routers.playground import _morceaux_par_recherche


class FauxClient:
    def __init__(self, documents):
        self.documents = documents
        self.appels = []

    async def search(self, collection, question, top_k=5):
        self.appels.append((collection, question, top_k))
        if self.documents is None:
            raise RuntimeError("OpenRAG muet")
        return {"documents": self.documents}


def test_les_morceaux_gardent_leur_identite_de_source():
    c = FauxClient([{"content": "# NATINF 7742-8552\n## NATINF 7987 — ACHAT…",
                     "metadata": {"filename": "natinf_07742_08552_106.md", "chunk_url": "https://x/extract/12",
                                  "file_url": "https://x/static/12", "page": 1, "content": "doublon ignoré"}}])
    morceaux = asyncio.run(_morceaux_par_recherche(c, "amorce-natinf", "NATINF 7987 ?"))
    assert len(morceaux) == 1
    m = morceaux[0]
    assert m["filename"] == "natinf_07742_08552_106.md" and m["chunk_url"] == "https://x/extract/12"
    assert m["content"].startswith("# NATINF"), "le contenu du document prime sur celui des métadonnées"
    assert c.appels == [("amorce-natinf", "NATINF 7987 ?", 5)]


def test_un_morceau_sans_contenu_n_est_pas_une_source():
    c = FauxClient([{"content": "", "metadata": {"filename": "vide.md"}}, {"content": "du texte", "metadata": {}}])
    assert len(asyncio.run(_morceaux_par_recherche(c, "x", "q"))) == 1


def test_une_recherche_en_echec_ne_casse_pas_la_reponse():
    assert asyncio.run(_morceaux_par_recherche(FauxClient(None), "x", "q")) == []
    assert asyncio.run(_morceaux_par_recherche(FauxClient([]), "x", "q")) == []
