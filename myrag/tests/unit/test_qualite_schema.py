"""paire_qa devient le jeu de questions : colonnes ajoutées, run_id facultatif, données gardées,
deux passages de migration sans effet de bord (les previews sont des SQLite existantes)."""

from __future__ import annotations

import asyncio
import sqlite3

from sqlalchemy.ext.asyncio import create_async_engine

from app import database

ANCIENNE = """CREATE TABLE paire_qa (
  id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36) NOT NULL, collection_name VARCHAR(255) NOT NULL,
  rang INTEGER, question TEXT NOT NULL, reponse TEXT NOT NULL, contextes_json TEXT, persona_nom VARCHAR(120),
  synthetiseur VARCHAR(60), style VARCHAR(60), longueur VARCHAR(20), relecture VARCHAR(20), commentaire TEXT,
  relu_par_hash VARCHAR(64), relu_le DATETIME, cree_le DATETIME)"""


_INSERT = (
    "INSERT INTO paire_qa (id, collection_name, rang, question, reponse, contextes_json, persona_nom, synthetiseur, "
    "style, longueur, relecture, commentaire, cree_le, source_ref, origine) "
    "VALUES (?, 'faq', 0, 'Q', 'R', '[]', '', '', '', '', 'brut', '', '2026-10-15', ?, ?)"
)


async def _migrer(url):
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
        for col, lite, pg in database._COLONNES_QUESTIONS:
            await database._migrate_add_column(conn, col, lite, pg, table="paire_qa")
        await database._rendre_run_id_facultatif(conn)
        await database._creer_index_questions(conn)
    await eng.dispose()


def test_une_base_ancienne_est_migree_sans_perte(tmp_path):
    chemin = tmp_path / "ancienne.db"
    con = sqlite3.connect(chemin)
    con.execute(ANCIENNE)
    # Une ligne telle que l'application l'écrivait (les colonnes optionnelles laissées vides).
    con.execute(
        "INSERT INTO paire_qa (id, run_id, collection_name, rang, question, reponse, relecture, relu_le, cree_le) "
        "VALUES ('p1', 'r1', 'faq', 0, 'Quel délai ?', 'Deux mois.', 'valide', '2026-10-14 10:00:00', '2026-10-14 09:00:00')"
    )
    con.commit()
    con.close()

    for _ in range(2):  # deux démarrages de suite
        asyncio.run(_migrer(f"sqlite+aiosqlite:///{chemin}"))

    con = sqlite3.connect(chemin)
    colonnes = {c[1]: c for c in con.execute("PRAGMA table_info(paire_qa)")}
    assert {"origine", "source_ref", "fiable", "hors_sujet", "dernier_verdict", "modifie_le"} <= set(colonnes)
    assert colonnes["run_id"][3] == 0, "run_id doit être facultatif"
    ligne = con.execute("SELECT id, run_id, question, origine, fiable, must_cite_json FROM paire_qa").fetchall()
    assert ligne == [("p1", "r1", "Quel délai ?", "generee", 0, "[]")]
    con.execute(_INSERT, ("p2", None, "saisie"))  # sans run : accepté
    index = {r[1] for r in con.execute("PRAGMA index_list(paire_qa)")}
    assert {"paire_qa_source_ref", "paire_qa_collection_origine"} <= index
    con.execute(_INSERT, ("p3", "x:1", "importee"))
    try:
        con.execute(_INSERT, ("p4", "x:1", "importee"))
        raise AssertionError("source_ref doit être unique par collection")
    except sqlite3.IntegrityError:
        pass
    con.close()
