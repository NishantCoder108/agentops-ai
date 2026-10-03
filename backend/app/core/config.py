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
    database_echo: bool = False

    # Organization whose data the agent's business tools may read. Stand-in until authentication
    # provides the caller's organization; never taken from the LLM or the request body.
    default_organization_id: uuid.UUID | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url", "default_organization_id", "embedding_model", mode="before")
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

    @model_validator(mode="after")
    def check_production_safety(self) -> "Settings":
        if self.is_production:
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not contain '*' in production")
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
