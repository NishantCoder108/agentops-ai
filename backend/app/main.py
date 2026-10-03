from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import close_database, close_embedding_provider, close_llm_provider
from app.api.v1.router import api_v1_router
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.db.session import create_db_engine, create_session_factory
from app.rate_limit import create_rate_limiter
from app.schemas.error import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_llm_provider(app)
    await close_embedding_provider(app)
    await close_database(app)
    await app.state.rate_limiter.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        responses={500: {"model": ErrorResponse, "description": "Internal server error"}},
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.rate_limiter = create_rate_limiter(
        settings.redis_url.get_secret_value() if settings.redis_url is not None else None
    )
    app.state.llm_provider = None
    app.state.embedding_provider = None
    app.state.db_engine = create_db_engine(settings)
    app.state.db_session_factory = (
        create_session_factory(app.state.db_engine) if app.state.db_engine is not None else None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
