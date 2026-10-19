"""L'accueil, figé : la forme de /api/accueil/mes-collections et de /exemple. Le lot D les
fait évoluer dans sa PR, avec le diff du fichier figé."""

from __future__ import annotations

from tests.conftest import personne
from tests.non_regression._outils import figer, forme


def test_mes_collections_et_exemple(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    mc = client.get("/api/accueil/mes-collections")
    assert mc.status_code == 200, mc.text
    corps = mc.json()
    assert any(c["name"] == nom for c in corps["collections"])
    corps["collections"] = [c for c in corps["collections"] if c["name"] == nom]
    figer("accueil/mes_collections", forme(corps))
    ex = client.get("/api/accueil/exemple")
    assert ex.status_code == 200 and set(ex.json()) == {"exemple"}
