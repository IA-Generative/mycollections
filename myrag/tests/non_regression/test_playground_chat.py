"""Le bac à sable, figé : la forme de la réponse de /chat, et le fait qu'une question posée
n'entre PAS dans le jeu de questions (lot E : ce qui change doit se décider, pas se glisser)."""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import AsyncMock, patch

from app.services.reponse import Reponse
from tests.conftest import personne
from tests.non_regression._outils import figer, forme

CLES = {"response", "mention", "sources", "source_names", "model", "system_prompt_used", "fallback_used", "repli_recherche"}


def _compter(table: str, nom: str) -> int:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return con.execute(f"SELECT count(*) FROM {table} WHERE collection_name = ?", (nom,)).fetchone()[0]
    finally:
        con.close()


def test_forme_de_la_reponse_et_rien_dans_le_jeu(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    rep = Reponse(
        contenu="Deux mois.",
        sources=[{"filename": "delais.md", "content": "Le délai est de deux mois.", "page": 1}],
        source_names=["delais.md"],
        modele="openrag-test",
    )
    with patch("app.routers.playground.OpenRAGClient") as cls, patch("app.routers.playground.repondre", AsyncMock(return_value=rep)):
        cls.return_value.health_check = AsyncMock(return_value=True)
        r = client.post(f"/api/playground/{nom}/chat", json={"question": "Quel est le délai ?"})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert set(corps) == CLES
    figer("playground/chat", forme(corps))
    assert _compter("paire_qa", nom) == 0, "une question posée au bac à sable n'entre pas dans le jeu (comportement actuel)"
    assert _compter("usage_question", nom) == 1, "la mesure d'usage compte la question, sans son texte"
