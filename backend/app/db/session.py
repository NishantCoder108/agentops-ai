from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


def create_db_engine(settings: Settings) -> AsyncEngine | None:
    """Create the engine, or return None when DATABASE_URL is unset. No connection is opened here."""
    if settings.database_url is None:
        return None
    return create_async_engine(
        settings.database_url.get_secret_value(),
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: attributes stay readable after commit instead of
    # triggering a lazy reload, which is not possible implicitly in async code.
    return async_sessionmaker(engine, expire_on_commit=False)
