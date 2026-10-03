from collections.abc import Sequence
from typing import Protocol

import openai
from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.exceptions import AppError
from app.llm.providers.openrouter import DEFAULT_BASE_URL

# Must match the document_chunks.embedding column.
EMBEDDING_DIMENSIONS = 1536


class EmbeddingError(AppError):
    status_code = 502
    code = "embedding_error"


class EmbeddingConfigurationError(EmbeddingError):
    status_code = 500
    code = "embedding_not_configured"

    def __init__(self) -> None:
        super().__init__(
            "Embedding model is not configured",
            details={"missing_env_vars": ["EMBEDDING_MODEL", "OPENROUTER_API_KEY"]},
        )


class EmbeddingProviderError(EmbeddingError):
    status_code = 502
    code = "embedding_provider_error"


class EmbeddingProvider(Protocol):
    """Turns texts into vectors. Implementations must not raise provider SDK errors."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def aclose(self) -> None: ...


class OpenRouterEmbeddingProvider:
    """Embeddings via OpenRouter's OpenAI-compatible embeddings API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        dimensions: int = EMBEDDING_DIMENSIONS,
        http_client: object | None = None,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=2,
            http_client=http_client,  # type: ignore[arg-type]
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(model=self._model, input=list(texts))
        except openai.APITimeoutError as exc:
            raise EmbeddingProviderError(
                "Embedding provider timed out", code="embedding_timeout", status_code=504
            ) from exc
        except openai.APIError as exc:
            raise EmbeddingProviderError("Embedding provider returned an error") from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts) or any(len(vector) != self._dimensions for vector in vectors):
            raise EmbeddingProviderError(
                f"Embedding provider must return {self._dimensions}-dimensional vectors"
            )
        return vectors

    async def aclose(self) -> None:
        await self._client.close()


def create_embedding_provider(settings: Settings) -> OpenRouterEmbeddingProvider:
    api_key = settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else ""
    if not settings.embedding_model or not api_key:
        raise EmbeddingConfigurationError()
    return OpenRouterEmbeddingProvider(
        api_key=api_key,
        model=settings.embedding_model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
