import uuid
from enum import Enum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ASYNC_POSTGRES_SCHEME = "postgresql+asyncpg://"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LLMProviderName(str, Enum):
    OPENROUTER = "openrouter"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AgentOps AI"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    llm_provider: LLMProviderName = LLMProviderName.OPENROUTER
    llm_model: str | None = None
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Embedding model for document search, e.g. openai/text-embedding-3-small. Uses OPENROUTER_API_KEY.
    embedding_model: str | None = None

    # SecretStr because the URL contains the database password.
    database_url: SecretStr | None = None
    # SQL echo writes statement text, which can include row values. Off in production.
    database_echo: bool = False

    # HS256 key for access tokens. Required in production. At least 32 characters.
    jwt_secret: SecretStr | None = None
    jwt_access_token_minutes: int = 60

    # Chat rate-limit counters only. Leave empty in development to count in this process.
    # Required in production so every worker shares one limit. Never store PostgreSQL data here.
    redis_url: SecretStr | None = None
    chat_rate_limit_requests: int = 20
    chat_rate_limit_window_seconds: int = 60
    # Sign-in and registration attempts for one email address.
    auth_rate_limit_requests: int = 10
    auth_rate_limit_window_seconds: int = 300
    # New accounts across every email address, so registration cannot run without a cap.
    register_rate_limit_requests: int = 20
    register_rate_limit_window_seconds: int = 60

    # Kept so existing environment files still load. Authorization uses the authenticated user's
    # organization, never this value, the LLM, or the request body.
    default_organization_id: uuid.UUID | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "database_url",
        "default_organization_id",
        "embedding_model",
        "jwt_secret",
        "redis_url",
        mode="before",
    )
    @classmethod
    def empty_string_is_unset(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def check_database_driver(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith(ASYNC_POSTGRES_SCHEME):
            raise ValueError(f"DATABASE_URL must start with {ASYNC_POSTGRES_SCHEME!r}")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def check_jwt_secret_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value

    @field_validator("jwt_access_token_minutes")
    @classmethod
    def check_token_lifetime(cls, value: int) -> int:
        if not 1 <= value <= 24 * 60:
            raise ValueError("JWT_ACCESS_TOKEN_MINUTES must be between 1 and 1440")
        return value

    @field_validator("redis_url")
    @classmethod
    def check_redis_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        url = value.get_secret_value()
        if not url.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return value

    @field_validator("chat_rate_limit_requests")
    @classmethod
    def check_chat_rate_limit_requests(cls, value: int) -> int:
        if not 1 <= value <= 10_000:
            raise ValueError("CHAT_RATE_LIMIT_REQUESTS must be between 1 and 10000")
        return value

    @field_validator("chat_rate_limit_window_seconds")
    @classmethod
    def check_chat_rate_limit_window(cls, value: int) -> int:
        if not 1 <= value <= 24 * 60 * 60:
            raise ValueError("CHAT_RATE_LIMIT_WINDOW_SECONDS must be between 1 and 86400")
        return value

    @field_validator("auth_rate_limit_requests", "register_rate_limit_requests")
    @classmethod
    def check_auth_rate_limit_requests(cls, value: int) -> int:
        if not 1 <= value <= 10_000:
            raise ValueError("Auth rate limit requests must be between 1 and 10000")
        return value

    @field_validator("auth_rate_limit_window_seconds", "register_rate_limit_window_seconds")
    @classmethod
    def check_auth_rate_limit_window(cls, value: int) -> int:
        if not 1 <= value <= 24 * 60 * 60:
            raise ValueError("Auth rate limit window must be between 1 and 86400 seconds")
        return value

    @model_validator(mode="after")
    def check_production_safety(self) -> "Settings":
        if self.is_production:
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.database_echo:
                raise ValueError("DATABASE_ECHO must be false in production")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not contain '*' in production")
            if self.jwt_secret is None:
                raise ValueError("JWT_SECRET must be set in production")
            if self.redis_url is None:
                raise ValueError("REDIS_URL must be set in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
