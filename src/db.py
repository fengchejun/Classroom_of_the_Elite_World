from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
