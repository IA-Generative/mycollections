"""La reprise des collections nées avant le titre : trois sources, et jamais d'écrasement."""

import asyncio
import os
import sqlite3

import pytest


def _sql(requete, params=()):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        lignes = con.execute(requete, params).fetchall()
        con.commit()
        return lignes
    finally:
        con.close()


def _rejouer():
    from app.database import _retro_remplir_titres, engine

    async def _f():
        async with engine.begin() as conn:
            await _retro_remplir_titres(conn)
    asyncio.run(_f())


NOMS = ("amorce-rne-elus", "demo-reprise-alias", "demo-reprise-defaut", "dgef-reprise-nom", "reprise-deja-titree")


@pytest.fixture
def anciennes(client, purger):
    for n in NOMS:
        purger(n)
    from app.services.collection_store import create_collection

    async def _creer():
        for n in NOMS:
            await create_collection({"name": n})
    asyncio.run(_creer())
    _sql(f"UPDATE collections SET titre = '' WHERE name IN ({','.join('?' * len(NOMS))})", NOMS)
    _sql("UPDATE collections SET titre = 'Saisi à la main' WHERE name = 'reprise-deja-titree'")
    from app.database import async_session
    from app.models.db import Publication

    async def _publier():
        async with async_session() as session:
            session.add(Publication(collection_name="demo-reprise-alias", state="published",
                                    alias_name="📚 Marchés publics — seuils 2026"))
            session.add(Publication(collection_name="demo-reprise-defaut", state="published",
                                    alias_name="📚 demo-reprise-defaut"))
            await session.commit()
    asyncio.run(_publier())
    yield
    for n in NOMS:
        purger(n)


def _titres():
    return dict(_sql(f"SELECT name, titre FROM collections WHERE name IN ({','.join('?' * len(NOMS))})", NOMS))


def test_trois_sources_par_ordre_de_confiance(anciennes):
    _rejouer()
    t = _titres()
    assert t["amorce-rne-elus"] == "Répertoire national des élus", "le catalogue des amorces d'abord"
    assert t["demo-reprise-alias"] == "Marchés publics — seuils 2026", "puis le nom posé à la publication"
    assert t["demo-reprise-defaut"] == "Reprise defaut", "un alias qui n'est que l'identifiant ne compte pas"
    assert t["dgef-reprise-nom"] == "DGEF reprise nom", "à défaut, l'identifiant rendu lisible"


def test_un_titre_saisi_n_est_jamais_ecrase_et_rejouer_ne_change_rien(anciennes):
    _rejouer()
    premier = _titres()
    assert premier["reprise-deja-titree"] == "Saisi à la main"
    _sql("UPDATE collections SET titre = 'Corrigé par le garant' WHERE name = 'dgef-reprise-nom'")
    _rejouer()
    second = _titres()
    assert second["dgef-reprise-nom"] == "Corrigé par le garant"
    assert {k: v for k, v in second.items() if k != "dgef-reprise-nom"} == {k: v for k, v in premier.items() if k != "dgef-reprise-nom"}


def test_une_amorce_nait_avec_son_titre_et_sa_rubrique(client, en_tant_que, purger, monkeypatch):
    from app.routers import amorces as routeur
    from tests.conftest import SUPERADMIN
    monkeypatch.delitem(routeur.CONNECTEURS, "natinfo")
    purger("amorce-natinf")
    en_tant_que(SUPERADMIN)
    client.post("/api/amorces/natinf/import")  # 501 : le connecteur manque, mais la fiche est préparée
    fiche = client.get("/api/collections/amorce-natinf").json()
    assert fiche["titre"] == "Codes NATINF" and fiche["categorie"] == "securite-delinquance"
    purger("amorce-natinf")
