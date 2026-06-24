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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_add_archived_at(conn)
        await _migrate_add_column(conn, "created_by", "VARCHAR(255)", "VARCHAR(255)")
        await _migrate_add_column(conn, "scope_groups_json", "TEXT", "TEXT")


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


async def _migrate_add_column(conn, column: str, sqlite_type: str, pg_type: str):
    """Add a collections.<column> if missing (SQLite + PostgreSQL compatible)."""
    from sqlalchemy import text

    def _sync(sync_conn):
        dialect = sync_conn.dialect.name
        if dialect == "sqlite":
            rows = sync_conn.exec_driver_sql("PRAGMA table_info(collections)").fetchall()
            cols = {r[1] for r in rows}
            if column not in cols:
                sync_conn.exec_driver_sql(
                    f"ALTER TABLE collections ADD COLUMN {column} {sqlite_type}"
                )
        else:
            sync_conn.execute(text(
                f"ALTER TABLE collections ADD COLUMN IF NOT EXISTS {column} {pg_type}"
            ))

    await conn.run_sync(_sync)


async def get_session() -> AsyncSession:
    """Get a database session (for use with FastAPI Depends)."""
    async with async_session() as session:
        yield session
