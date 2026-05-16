from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _migrate_schema(connection) -> None:
    """Add missing columns to existing tables (idempotent)."""
    import sqlite3
    from pathlib import Path

    # Only applies to SQLite
    try:
        engine_driver = connection.engine.url.get_backend_name()
    except Exception:
        engine_driver = ""
    if engine_driver != "sqlite":
        return

    # Get the database file path from the connection URL
    db_path = str(connection.engine.url).replace("sqlite+aiosqlite:///", "")
    if not Path(db_path).exists():
        return

    raw_conn = sqlite3.connect(db_path)
    try:
        cursor = raw_conn.execute("PRAGMA table_info(characters)")
        columns = {row[1] for row in cursor.fetchall()}
        if "private_points" not in columns:
            raw_conn.execute(
                "ALTER TABLE characters ADD COLUMN private_points INTEGER DEFAULT 100000"
            )
        if "spending_habit" not in columns:
            raw_conn.execute(
                "ALTER TABLE characters ADD COLUMN spending_habit VARCHAR(32) DEFAULT 'normal'"
            )
        raw_conn.commit()
    finally:
        raw_conn.close()


async def init_db() -> None:
    from src.models.base import Base
    # Import all models to register them with Base.metadata
    import src.models.character  # noqa: F401
    import src.models.dialogue  # noqa: F401
    import src.models.event  # noqa: F401
    import src.models.game_session  # noqa: F401
    import src.models.location  # noqa: F401
    import src.models.secret  # noqa: F401
    import src.models.social_relation  # noqa: F401
    import src.models.transaction  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(_migrate_schema)
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
