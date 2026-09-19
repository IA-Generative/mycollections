"""Database engine and session management for MyRAG.

Supports SQLite (dev) and PostgreSQL (prod) via DATABASE_URL:
  - sqlite+aiosqlite:///app/data/myrag.db  (default)
  - postgresql+asyncpg://user:pass@host:5432/myrag
"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Ensure the data directory exists for SQLite
if "sqlite" in settings.database_url:
    db_path = settings.database_url.split("///")[-1]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite needs this for concurrent access
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables + lightweight in-place migrations. Called on startup."""
    import app.models.db  # noqa: F401 — sans cet import, create_all ne connaît aucune table
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_add_archived_at(conn)
        await _migrate_add_column(conn, "created_by", "VARCHAR(255)", "VARCHAR(255)")
        await _migrate_add_column(conn, "scope_groups_json", "TEXT", "TEXT")
        # Circuit collaboratif (ADR-0001). `DEFAULT ''` est côté SQL, exprès : sans lui
        # les lignes existantes recevraient NULL, le défaut du modèle étant côté Python.
        await _migrate_add_column(conn, "etat_collab", "VARCHAR(30)", "VARCHAR(30)")
        await _migrate_add_column(conn, "garant_hash", "VARCHAR(64)", "VARCHAR(64)")
        await _migrate_add_column(
            conn, "garant_pressenti", "VARCHAR(255) DEFAULT ''", "VARCHAR(255) DEFAULT ''"
        )
        await _migrate_add_column(conn, "demande_id", "VARCHAR(36)", "VARCHAR(36)")
        await _retro_remplir_etat_collab(conn)
        # Titre affiché et catégorie (l'identifiant technique ne se lit plus à l'écran).
        await _migrate_add_column(conn, "titre", "VARCHAR(255) DEFAULT ''", "VARCHAR(255) DEFAULT ''")
        await _migrate_add_column(conn, "categorie", "VARCHAR(64)", "VARCHAR(64)")
        await _retro_remplir_titres(conn)
        await _semer_categories(conn)


async def _retro_remplir_titres(conn):
    """Donne un titre lisible aux collections qui n'en ont pas.

    Trois sources, de la plus sûre à la moins sûre : le catalogue des amorces (titre
    rédigé), le nom posé à la publication (débarrassé de ses marques), l'identifiant
    (préfixe de provenance retiré). Idempotent : ne touche que les titres vides — un
    titre saisi n'est jamais écrasé.
    """
    from sqlalchemy import text

    from app.amorces import charger_catalogue
    from app.services.nommage import titre_depuis_alias, titre_depuis_nom

    sans_titre = [r[0] for r in (await conn.execute(text(
        "SELECT name FROM collections WHERE titre IS NULL OR titre = ''"
    ))).fetchall()]
    if not sans_titre:
        return
    du_catalogue = {e["collection"]: e.get("titre", "") for e in charger_catalogue()}
    alias = {r[0]: r[1] for r in (await conn.execute(text(
        "SELECT collection_name, alias_name FROM publications"
    ))).fetchall()}
    for name in sans_titre:
        titre = (du_catalogue.get(name) or titre_depuis_alias(alias.get(name), name)
                 or titre_depuis_nom(name))
        await conn.execute(text("UPDATE collections SET titre = :t WHERE name = :n"),
                           {"t": titre[:255], "n": name})


async def _semer_categories(conn):
    """Au premier démarrage seulement (table vide) : les rubriques de départ, et le
    classement que le catalogue des amorces propose. Ensuite, tout se règle à l'écran
    d'administration — un redémarrage ne reclasse jamais rien."""
    from sqlalchemy import text

    from app.amorces import charger_catalogue
    from app.services.categorie_store import CATEGORIES_DE_DEPART

    if (await conn.execute(text("SELECT COUNT(*) FROM categories"))).scalar():
        return
    for ordre, (cle, libelle, description) in enumerate(CATEGORIES_DE_DEPART, start=1):
        await conn.execute(
            text("INSERT INTO categories (cle, libelle, description, ordre, cree_le) "
                 "VALUES (:c, :l, :d, :o, CURRENT_TIMESTAMP)"),
            {"c": cle, "l": libelle, "d": description, "o": ordre * 10},
        )
    cles = {c[0] for c in CATEGORIES_DE_DEPART}
    for e in charger_catalogue():
        if e.get("categorie") in cles:
            await conn.execute(
                text("UPDATE collections SET categorie = :c WHERE name = :n AND categorie IS NULL"),
                {"c": e["categorie"], "n": e["collection"]},
            )


async def _retro_remplir_etat_collab(conn):
    """Donne un état du circuit collaboratif aux collections qui l'ont précédé.

    Décision PO du 2026-09-13 : une collection déjà publiée « tout le monde » est
    « publiée à tous » ; toute autre collection sans état est « publiée au groupe ».
    Rien ne change pour les testeurs, et la règle « jamais servie hors de son groupe
    sans être publiée à tous » vaut dès le premier démarrage. Idempotent : ne touche
    que les lignes à NULL.
    """
    from sqlalchemy import text

    await conn.execute(text(
        "UPDATE collections SET etat_collab = 'publiee_tous' "
        "WHERE etat_collab IS NULL AND name IN ("
        "  SELECT collection_name FROM publications "
        "  WHERE state = 'published' AND visibility = 'all')"
    ))
    await conn.execute(text(
        "UPDATE collections SET etat_collab = 'publiee_groupe' WHERE etat_collab IS NULL"
    ))


async def _migrate_add_archived_at(conn):
    """Add collections.archived_at if missing (SQLite + PostgreSQL compatible)."""
    from sqlalchemy import text

    def _sync(sync_conn):
        dialect = sync_conn.dialect.name
        if dialect == "sqlite":
            rows = sync_conn.exec_driver_sql("PRAGMA table_info(collections)").fetchall()
            cols = {r[1] for r in rows}
            if "archived_at" not in cols:
                sync_conn.exec_driver_sql("ALTER TABLE collections ADD COLUMN archived_at DATETIME")
        else:
            sync_conn.execute(text(
                "ALTER TABLE collections ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP"
            ))

    await conn.run_sync(_sync)


async def _migrate_add_column(
    conn, column: str, sqlite_type: str, pg_type: str, table: str = "collections"
):
    """Add a <table>.<column> if missing (SQLite + PostgreSQL compatible).

    `table` et `column` ne viennent que d'appels littéraux de ce module — jamais
    d'une entrée utilisateur.
    """
    from sqlalchemy import text

    def _sync(sync_conn):
        dialect = sync_conn.dialect.name
        if dialect == "sqlite":
            rows = sync_conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            cols = {r[1] for r in rows}
            if column not in cols:
                sync_conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_type}"
                )
        else:
            sync_conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {pg_type}"
            ))

    await conn.run_sync(_sync)


async def get_session() -> AsyncSession:
    """Get a database session (for use with FastAPI Depends)."""
    async with async_session() as session:
        yield session
