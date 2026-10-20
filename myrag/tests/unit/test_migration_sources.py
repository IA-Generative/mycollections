"""ADR-0005 : la sensibilité d'une source se garde par fichier (source_files.sensitivity),
pour que la réindexation la reprenne. Les bases existantes la récupèrent du dernier dépôt
qui la concerne — ingest_jobs la gardait, pas les fichiers — et un choix posé après coup
n'est jamais écrasé par un redémarrage."""

from __future__ import annotations

import asyncio
import sqlite3

from sqlalchemy.ext.asyncio import create_async_engine

from app import database

#: source_files telle qu'elle était avant l'ADR-0005 (sans la colonne sensitivity).
ANCIENNE = """CREATE TABLE source_files (
  id INTEGER PRIMARY KEY, collection_name VARCHAR(255), filename VARCHAR(500),
  original_url TEXT, storage_path TEXT, file_size INTEGER, content_type VARCHAR(255),
  checksum VARCHAR(64), strategy_used VARCHAR(50), chunks_produced INTEGER,
  last_indexed_at DATETIME, created_at DATETIME)"""


async def _creer(url):
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    await eng.dispose()


async def _demarrer(url):
    """Ce que fait l'application à chaque démarrage : create_all puis la migration."""
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
        await database._migrer_sensibilite_sources(conn)
    await eng.dispose()


def test_les_sources_existantes_reprennent_la_sensibilite_de_leur_dernier_depot(tmp_path):
    chemin = tmp_path / "ancienne.db"
    con = sqlite3.connect(chemin)
    con.execute(ANCIENNE)
    con.execute("INSERT INTO source_files (collection_name, filename, storage_path) VALUES ('c1', 'note.md', '/x/note.md')")
    con.execute("INSERT INTO source_files (collection_name, filename, storage_path) VALUES ('c1', 'rapport.pdf', '/x/rapport.pdf')")
    con.execute("INSERT INTO source_files (collection_name, filename, storage_path) VALUES ('c2', 'seul.txt', '/x/seul.txt')")
    con.commit()
    con.close()
    asyncio.run(_creer(f"sqlite+aiosqlite:///{chemin}"))  # create_all : ingest_jobs et le reste, sans toucher source_files

    # Les dépôts d'avant gardaient la sensibilité dans ingest_jobs — deux pour note.md,
    # c'est la plus récente qui compte ; aucun pour seul.txt.
    con = sqlite3.connect(chemin)
    con.executemany(
        "INSERT INTO ingest_jobs (job_id, collection_name, filename, source_path, strategy, sensitivity, status, "
        "total_chunks, uploaded_chunks, failed_chunks, created_at) VALUES (?, 'c1', ?, '', ?, ?, 'done', 1, 1, 0, ?)",
        [
            ("j1", "note.md", "section", "internal", "2026-10-01 10:00:00"),
            ("j2", "note.md", "section", "confidential", "2026-10-05 10:00:00"),
            ("j3", "rapport.pdf", "openrag", "restricted", "2026-10-02 10:00:00"),
        ],
    )
    con.commit()
    con.close()

    asyncio.run(_demarrer(f"sqlite+aiosqlite:///{chemin}"))  # premier démarrage : colonne ajoutée, sensibilités reprises

    con = sqlite3.connect(chemin)
    sens = dict(con.execute("SELECT filename, sensitivity FROM source_files").fetchall())
    con.close()
    assert sens == {"note.md": "confidential", "rapport.pdf": "restricted", "seul.txt": "public"}, sens


def test_un_choix_pose_apres_coup_n_est_pas_ecrase_par_un_redemarrage(tmp_path):
    chemin = tmp_path / "ancienne.db"
    con = sqlite3.connect(chemin)
    con.execute(ANCIENNE)
    con.execute("INSERT INTO source_files (collection_name, filename, storage_path) VALUES ('c1', 'note.md', '/x/note.md')")
    con.commit()
    con.close()
    asyncio.run(_demarrer(f"sqlite+aiosqlite:///{chemin}"))  # premier démarrage : « public », sans dépôt connu

    con = sqlite3.connect(chemin)
    con.execute("UPDATE source_files SET sensitivity='internal' WHERE filename='note.md'")  # un choix posé par fichier
    con.commit()
    con.close()
    asyncio.run(_demarrer(f"sqlite+aiosqlite:///{chemin}"))  # redémarrage : rien ne bouge

    con = sqlite3.connect(chemin)
    assert con.execute("SELECT sensitivity FROM source_files WHERE filename='note.md'").fetchone()[0] == "internal"
    con.close()
