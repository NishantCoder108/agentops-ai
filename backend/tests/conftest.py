from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

# One module can belong to more than one layer. `pytest -m api` still runs each test once.
_UNIT_MARKS: dict[str, tuple[str, ...]] = {
    "test_chat_api.py": ("api",),
    "test_chat_stream_api.py": ("api",),
    "test_auth.py": ("api",),
    "test_health.py": ("api",),
    "test_errors.py": ("api",),
    "test_config.py": ("api",),
    "test_rate_limit.py": ("api", "service"),
    "test_database_config.py": ("service",),
    "test_llm_service.py": ("service",),
    "test_llm_factory.py": ("service",),
    "test_knowledge.py": ("service",),
    "test_openrouter_provider.py": ("service",),
    "test_agent_service.py": ("agent",),
    "test_agent_stream.py": ("agent",),
    "test_agent_grounding.py": ("agent",),
    "test_agent_tracking.py": ("agent",),
    "test_agent_run_presentation.py": ("agent",),
    "test_calculator_tool.py": ("tool",),
    "test_tool_registry.py": ("tool",),
    "test_analytics_input.py": ("tool",),
}

_DB_MARKS: dict[str, tuple[str, ...]] = {
    "test_auth.py": ("api", "db"),
    "test_agent_runs_api.py": ("api", "agent", "db"),
    "test_agent_tracking.py": ("agent", "db"),
    "test_knowledge.py": ("service", "db"),
    "test_chat_stream.py": ("api", "agent", "db"),
    "test_analytics.py": ("service", "db"),
    "test_session_dependency.py": ("api", "db"),
    "test_models.py": ("db",),
    "test_migrations.py": ("db",),
}


def make_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    missing: set[str] = set()
    for item in items:
        path = getattr(item, "path", None)
        if not isinstance(path, Path):
            continue
        marks = _marks_for(path)
        if not marks:
            missing.add(str(path))
            continue
        for mark in marks:
            item.add_marker(getattr(pytest.mark, mark))
    if missing:
        names = ", ".join(sorted(missing))
        raise pytest.UsageError(f"Test modules need a layer marker in tests/conftest.py: {names}")


def _marks_for(path: Path) -> tuple[str, ...]:
    table = _DB_MARKS if "db" in path.parts else _UNIT_MARKS
    return table.get(path.name, ())
