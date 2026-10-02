from app.core.exceptions import AppError


class LLMError(AppError):
    status_code = 502
    code = "llm_error"


class LLMConfigurationError(LLMError):
    status_code = 500
    code = "llm_not_configured"


class LLMProviderError(LLMError):
    status_code = 502
    code = "llm_provider_error"
