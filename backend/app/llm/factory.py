from app.core.config import LLMProviderName, Settings
from app.llm.base import LLMProvider
from app.llm.errors import LLMConfigurationError
from app.llm.providers.openrouter import OpenRouterProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == LLMProviderName.OPENROUTER:
        return _create_openrouter_provider(settings)
    raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")


def _create_openrouter_provider(settings: Settings) -> OpenRouterProvider:
    api_key = settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else ""
    model = settings.llm_model or ""

    missing = [name for name, value in (("OPENROUTER_API_KEY", api_key), ("LLM_MODEL", model)) if not value]
    if missing:
        raise LLMConfigurationError(
            "LLM provider 'openrouter' is not configured",
            details={"missing_env_vars": missing},
        )

    return OpenRouterProvider(
        api_key=api_key,
        model=model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        app_name=settings.app_name,
    )
