from pgvector.asyncpg import register_vector
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


async def _register_vector(connection: object) -> None:
    """Teach asyncpg the vector type. Ignored until the pgvector extension exists."""
    try:
        await register_vector(connection)  # type: ignore[arg-type]
    except ValueError as exc:
        if not str(exc).startswith("unknown type:"):
            raise


def prepare_engine(engine: AsyncEngine) -> AsyncEngine:
    @event.listens_for(engine.sync_engine, "connect")
    def register_vector_codec(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.run_async(_register_vector)  # type: ignore[attr-defined]

    return engine


def create_db_engine(settings: Settings) -> AsyncEngine | None:
    """Create the engine, or return None when DATABASE_URL is unset. No connection is opened here."""
    if settings.database_url is None:
        return None
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=settings.database_echo,
        pool_pre_ping=True,
    )
    return prepare_engine(engine)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: attributes stay readable after commit instead of
    # triggering a lazy reload, which is not possible implicitly in async code.
    return async_sessionmaker(engine, expire_on_commit=False)
