"""Le catalogue : chaque collection porte l'avis de ses usagers et sa dernière mise à jour,
calculés en requêtes groupées (le catalogue en montre des dizaines)."""

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event

from app.auth import CurrentUser
from app.models.db import utcnow
from tests.conftest import personne


def _sql(requete, params=()):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        lignes = con.execute(requete, params).fetchall()
        con.commit()
        return lignes
    finally:
        con.close()


def _catalogue(client, qui, en_tant_que):
    en_tant_que(qui)
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.list_models = AsyncMock(side_effect=RuntimeError("OpenRAG absent"))
        r = client.get("/api/collections")
    assert r.status_code == 200, r.text
    return {c["name"]: c for c in r.json()["collections"]}


def _avis(client, en_tant_que, nom, notes):
    en_tant_que(personne("lecteur-catalogue"))
    for i, note in enumerate(notes):
        assert client.post("/api/feedback/ingest", json={"collection": nom, "question": f"Q{i} ?", "response": "R.", "rating": note}).status_code == 200


@contextmanager
def _requetes_feedback():
    from app.database import engine

    vues: list[str] = []

    def _ecouter(conn, cursor, statement, parameters, context, executemany):
        if re.search(r"\bFROM feedback\b", statement):
            vues.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _ecouter)
    try:
        yield vues
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _ecouter)


def test_chaque_collection_porte_ses_avis(client, en_tant_que, creer_collection, nom, purger):
    autre = nom[:-2] + "zz"
    purger(autre)
    try:
        creer_collection(nom)
        creer_collection(autre)
        _avis(client, en_tant_que, nom, [1, 1, 1, -1])
        cols = _catalogue(client, personne(3), en_tant_que)
        assert cols[nom]["avis"] == {"total": 4, "satisfaction_rate": 0.75}
        assert cols[autre]["avis"] == {"total": 0, "satisfaction_rate": None}
    finally:
        purger(autre)


def test_une_seule_requete_sur_les_avis_quel_que_soit_le_nombre_de_collections(client, en_tant_que, creer_collection, nom, purger):
    noms = [f"{nom[:-2]}{i:02d}" for i in range(4)]
    for n in noms:
        purger(n)
    try:
        for n in noms:
            creer_collection(n)
            _avis(client, en_tant_que, n, [1])
        with _requetes_feedback() as vues:
            cols = _catalogue(client, personne(3), en_tant_que)
        assert all(cols[n]["avis"]["total"] == 1 for n in noms)
        assert len(vues) == 1, vues
    finally:
        for n in noms:
            purger(n)


def test_un_depot_fait_avancer_la_mise_a_jour(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    _sql("UPDATE collections SET updated_at = datetime('now', '-10 days') WHERE name = ?", (nom,))
    avant = datetime.fromisoformat(_catalogue(client, personne(3), en_tant_que)[nom]["derniere_mise_a_jour"])
    assert utcnow() - avant > timedelta(days=9)
    _sql(
        "INSERT INTO source_files (collection_name, filename, original_url, storage_path, file_size, content_type, checksum, strategy_used, chunks_produced, created_at) VALUES (?, 'note.md', '', '/x', 1, 'text/markdown', '', 'auto', 0, datetime('now'))",
        (nom,),
    )
    apres = datetime.fromisoformat(_catalogue(client, personne(3), en_tant_que)[nom]["derniere_mise_a_jour"])
    assert apres > avant and utcnow() - apres < timedelta(minutes=5)


def test_une_collection_illisible_n_apparait_pas(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    _sql("UPDATE collections SET scope_groups_json = '[\"/g/un-autre-groupe\"]' WHERE name = ?", (nom,))
    etranger = CurrentUser(sub="etranger-catalogue", username="e", groups=["/g/ailleurs"])
    assert nom not in _catalogue(client, etranger, en_tant_que)


def test_le_reste_du_corps_ne_change_pas(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, titre="Codes d'essai")
    c = _catalogue(client, personne(3), en_tant_que)[nom]
    for cle in ("name", "titre", "categorie", "description", "publication", "mes_droits", "created_at", "updated_at"):
        assert cle in c, cle
