"""Database engine and session management for MyRAG.

Supports SQLite (dev) and PostgreSQL (prod) via DATABASE_URL:
  - sqlite+aiosqlite:///app/data/myrag.db  (default)
  - postgresql+asyncpg://user:pass@host:5432/myrag
"""

from collections.abc import AsyncIterator
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
        await _migrate_add_column(conn, "garant_pressenti", "VARCHAR(255) DEFAULT ''", "VARCHAR(255) DEFAULT ''")
        await _migrate_add_column(conn, "demande_id", "VARCHAR(36)", "VARCHAR(36)")
        await _retro_remplir_etat_collab(conn)
        # Titre affiché et catégorie (l'identifiant technique ne se lit plus à l'écran).
        await _migrate_add_column(conn, "titre", "VARCHAR(255) DEFAULT ''", "VARCHAR(255) DEFAULT ''")
        await _migrate_add_column(conn, "categorie", "VARCHAR(64)", "VARCHAR(64)")
        await _migrate_add_column(conn, "alias_description", "TEXT DEFAULT ''", "TEXT DEFAULT ''", table="publications")
        await _retro_remplir_titres(conn)
        await _semer_categories(conn)
        # Boucle de satisfaction des demandes (2026-09-21).
        await _migrate_add_column(conn, "confirmation_demandee_le", "DATETIME", "TIMESTAMP", table="demande")
        await _migrate_add_column(conn, "satisfaction", "VARCHAR(20)", "VARCHAR(20)", table="demande")
        await _migrate_add_column(conn, "motif_insatisfaction", "TEXT", "TEXT", table="demande")
        await _elargir_etats_demande(conn)
        await _elargir_objets_evenement(conn)
        # Jeu de questions de référence (docs/qualite.md) : paire_qa étendue.
        for col, lite, pg in _COLONNES_QUESTIONS:
            await _migrate_add_column(conn, col, lite, pg, table="paire_qa")
        await _rendre_run_id_facultatif(conn)
        await _creer_index_questions(conn)
        await _migrer_sensibilites(conn)


#: (colonne, type SQLite, type PostgreSQL) ajoutées à paire_qa pour le jeu de questions.
_COLONNES_QUESTIONS = (
    ("origine", "VARCHAR(20) DEFAULT 'generee'", "VARCHAR(20) DEFAULT 'generee'"),
    ("source_ref", "VARCHAR(120)", "VARCHAR(120)"),
    ("feedback_id", "INTEGER", "INTEGER"),
    ("must_cite_json", "TEXT DEFAULT '[]'", "TEXT DEFAULT '[]'"),
    ("tags_json", "TEXT DEFAULT '[]'", "TEXT DEFAULT '[]'"),
    ("hors_sujet", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
    ("fiable", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
    ("dernier_verdict", "VARCHAR(20)", "VARCHAR(20)"),
    ("derniere_mesure_le", "DATETIME", "TIMESTAMP"),
    ("derniere_mesure_id", "VARCHAR(36)", "VARCHAR(36)"),
    ("modifie_par_hash", "VARCHAR(64)", "VARCHAR(64)"),
    ("modifie_le", "DATETIME", "TIMESTAMP"),
    ("servie_fois", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
    ("servie_le", "DATETIME", "TIMESTAMP"),
)


async def _rendre_run_id_facultatif(conn):
    """paire_qa.run_id devient facultatif (une question saisie n'a pas de run).

    PostgreSQL : un ALTER suffit. SQLite ne sait pas retirer un NOT NULL : la table est
    reconstruite à l'identique, données comprises, si (et seulement si) la contrainte est encore
    là — les bases des previews sont des SQLite qui ont déjà la table."""

    def _sync(sync_conn):
        if sync_conn.dialect.name != "sqlite":
            sync_conn.exec_driver_sql("ALTER TABLE paire_qa ALTER COLUMN run_id DROP NOT NULL")
            return
        colonnes = sync_conn.exec_driver_sql("PRAGMA table_info(paire_qa)").fetchall()
        if not any(c[1] == "run_id" and c[3] for c in colonnes):  # c[3] = notnull
            return
        noms = [c[1] for c in colonnes]
        for (nom,) in sync_conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='paire_qa' AND sql IS NOT NULL").fetchall():
            sync_conn.exec_driver_sql(f'DROP INDEX IF EXISTS "{nom}"')
        sync_conn.exec_driver_sql("ALTER TABLE paire_qa RENAME TO paire_qa_avant_jeu")
        Base.metadata.tables["paire_qa"].create(sync_conn)
        table = Base.metadata.tables["paire_qa"]
        lus = []
        for nom in noms:
            col = table.c.get(nom)
            defaut = getattr(getattr(col, "default", None), "arg", None) if col is not None else None
            # Une colonne devenue obligatoire reprend sa valeur par défaut quand l'ancienne était vide.
            if col is not None and not col.nullable and isinstance(defaut, (str, int, float, bool)):
                valeur = f"'{defaut}'" if isinstance(defaut, str) else str(int(defaut) if isinstance(defaut, bool) else defaut)
                lus.append(f"COALESCE({nom}, {valeur})")
            elif col is not None and not col.nullable and nom in ("question", "reponse"):
                lus.append(f"COALESCE({nom}, '')")
            elif col is not None and not col.nullable and nom == "cree_le":
                lus.append("COALESCE(cree_le, CURRENT_TIMESTAMP)")
            else:
                lus.append(nom)
        sync_conn.exec_driver_sql(f"INSERT INTO paire_qa ({', '.join(noms)}) SELECT {', '.join(lus)} FROM paire_qa_avant_jeu")
        sync_conn.exec_driver_sql("DROP TABLE paire_qa_avant_jeu")

    await conn.run_sync(_sync)


async def _creer_index_questions(conn):
    """Les index du jeu de questions sur une table paire_qa qui existait déjà (create_all ne
    touche pas une table existante). Même syntaxe en SQLite et en PostgreSQL."""
    from sqlalchemy import text

    await conn.execute(text("CREATE INDEX IF NOT EXISTS paire_qa_collection_origine ON paire_qa (collection_name, origine)"))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS paire_qa_source_ref ON paire_qa (collection_name, source_ref)"))


async def _elargir_etats_demande(conn):
    """La contrainte `demande_etat_valide` d'une base existante ne connaît pas « a_confirmer » :
    `create_all` ne touche pas une table qui existe. On la repose à partir du modèle — toujours
    la même, donc idempotent. PostgreSQL seulement : SQLite ne modifie pas une contrainte, et ses
    bases (développement, tests) sont recréées."""
    from sqlalchemy import text

    from app.models.db import ETATS_DEMANDE, SATISFACTIONS

    def _sync(sync_conn):
        if sync_conn.dialect.name == "sqlite":
            return
        domaine = ", ".join(f"'{e}'" for e in ETATS_DEMANDE)
        sync_conn.execute(text("ALTER TABLE demande DROP CONSTRAINT IF EXISTS demande_etat_valide"))
        sync_conn.execute(text(f"ALTER TABLE demande ADD CONSTRAINT demande_etat_valide CHECK (etat IN ({domaine}))"))
        # Et la satisfaction, colonne ajoutée plus haut : même domaine que le modèle.
        satisfactions = ", ".join(f"'{v}'" for v in SATISFACTIONS)
        sync_conn.execute(text("ALTER TABLE demande DROP CONSTRAINT IF EXISTS demande_satisfaction_valide"))
        sync_conn.execute(text(f"ALTER TABLE demande ADD CONSTRAINT demande_satisfaction_valide CHECK (satisfaction IS NULL OR satisfaction IN ({satisfactions}))"))

    await conn.run_sync(_sync)


async def _elargir_objets_evenement(conn):
    """La contrainte `evenement_objet_valide` d'une base existante ne connaît pas « assistant »
    (ADR-0003) : reposée à partir du modèle, toujours la même, donc idempotente. PostgreSQL
    seulement, comme `_elargir_etats_demande`."""
    from sqlalchemy import text

    from app.models.db import OBJETS_EVENEMENT

    def _sync(sync_conn):
        if sync_conn.dialect.name == "sqlite":
            return
        domaine = ", ".join(f"'{e}'" for e in OBJETS_EVENEMENT)
        sync_conn.execute(text("ALTER TABLE evenement DROP CONSTRAINT IF EXISTS evenement_objet_valide"))
        sync_conn.execute(text(f"ALTER TABLE evenement ADD CONSTRAINT evenement_objet_valide CHECK (objet_type IN ({domaine}))"))

    await conn.run_sync(_sync)


async def _migrer_sensibilites(conn):
    """Réécrit les sensibilités d'avant la nouvelle liste (#134) : `confidential` et `secret`
    deviennent `restricted`, jamais un niveau moins protecteur. Idempotent : ne touche que les
    anciennes valeurs."""
    from sqlalchemy import text

    from app.services.chunker import ANCIENNES_SENSIBILITES

    for table in ("collections", "ingest_jobs"):
        for ancienne, nouvelle in ANCIENNES_SENSIBILITES.items():
            await conn.execute(text(f"UPDATE {table} SET sensitivity = :n WHERE sensitivity = :a"), {"n": nouvelle, "a": ancienne})


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

    sans_titre = [r[0] for r in (await conn.execute(text("SELECT name FROM collections WHERE titre IS NULL OR titre = ''"))).fetchall()]
    if not sans_titre:
        return
    du_catalogue = {e["collection"]: e.get("titre", "") for e in charger_catalogue()}
    alias = {r[0]: r[1] for r in (await conn.execute(text("SELECT collection_name, alias_name FROM publications"))).fetchall()}
    for name in sans_titre:
        titre = du_catalogue.get(name) or titre_depuis_alias(alias.get(name), name) or titre_depuis_nom(name)
        await conn.execute(text("UPDATE collections SET titre = :t WHERE name = :n"), {"t": titre[:255], "n": name})


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
            text("INSERT INTO categories (cle, libelle, description, ordre, cree_le) VALUES (:c, :l, :d, :o, CURRENT_TIMESTAMP)"),
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

    await conn.execute(
        text(
            "UPDATE collections SET etat_collab = 'publiee_tous' "
            "WHERE etat_collab IS NULL AND name IN ("
            "  SELECT collection_name FROM publications "
            "  WHERE state = 'published' AND visibility = 'all')"
        )
    )
    await conn.execute(text("UPDATE collections SET etat_collab = 'publiee_groupe' WHERE etat_collab IS NULL"))


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
            sync_conn.execute(text("ALTER TABLE collections ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP"))

    await conn.run_sync(_sync)


async def _migrate_add_column(conn, column: str, sqlite_type: str, pg_type: str, table: str = "collections"):
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
                sync_conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_type}")
        else:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {pg_type}"))

    await conn.run_sync(_sync)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Get a database session (for use with FastAPI Depends)."""
    async with async_session() as session:
        yield session
