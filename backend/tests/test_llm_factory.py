import pytest

from app.llm import LLMConfigurationError, create_llm_provider
from app.llm.providers.openrouter import OpenRouterProvider
from tests.conftest import make_settings


def test_creates_openrouter_provider_when_configured() -> None:
    settings = make_settings(
        llm_provider="openrouter", openrouter_api_key="test-key", llm_model="test/model"
    )

    provider = create_llm_provider(settings)

    assert isinstance(provider, OpenRouterProvider)
    assert provider.name == "openrouter"


def test_missing_openrouter_config_lists_missing_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(LLMConfigurationError) as exc_info:
        create_llm_provider(make_settings(llm_provider="openrouter"))

    assert exc_info.value.details == {"missing_env_vars": ["OPENROUTER_API_KEY", "LLM_MODEL"]}


def test_unknown_provider_is_rejected_by_settings() -> None:
    with pytest.raises(ValueError):
        make_settings(llm_provider="does-not-exist")
