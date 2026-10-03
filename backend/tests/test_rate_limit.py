import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import RedisError

from app.api.dependencies import get_current_user, get_llm_provider
from app.main import create_app
from app.models import UserRole
from app.rate_limit import (
    MemoryCounterStore,
    RateLimiter,
    RateLimitUnavailableError,
    RedisCounterStore,
    create_rate_limiter,
)
from tests.auth_helpers import install_user
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider

pytestmark = pytest.mark.anyio


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _FakeRedis:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.closed = False

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        self.calls.append((script, numkeys, keys_and_args))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def aclose(self) -> None:
        self.closed = True


def _limiter(clock: _Clock) -> RateLimiter:
    return RateLimiter(MemoryCounterStore(clock), clock)


async def test_memory_limiter_allows_requests_inside_the_window() -> None:
    limiter = _limiter(_Clock(1_000.0))

    first = await limiter.consume("chat", "user-a", limit=2, window_seconds=60)
    second = await limiter.consume("chat", "user-a", limit=2, window_seconds=60)

    assert first.allowed is True
    assert second.allowed is True


async def test_memory_limiter_blocks_the_next_request_until_the_window_ends() -> None:
    clock = _Clock(1_000.0)
    limiter = _limiter(clock)

    await limiter.consume("chat", "user-a", limit=2, window_seconds=60)
    await limiter.consume("chat", "user-a", limit=2, window_seconds=60)
    blocked = await limiter.consume("chat", "user-a", limit=2, window_seconds=60)

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 20

    clock.now += 20
    opened = await limiter.consume("chat", "user-a", limit=2, window_seconds=60)
    assert opened.allowed is True


async def test_memory_limiter_counts_users_separately() -> None:
    limiter = _limiter(_Clock(1_000.0))

    await limiter.consume("chat", "user-a", limit=1, window_seconds=60)
    other = await limiter.consume("chat", "user-b", limit=1, window_seconds=60)

    assert other.allowed is True


async def test_redis_limiter_sends_one_increment_and_uses_the_returned_ttl() -> None:
    redis = _FakeRedis([3, 12])
    limiter = RateLimiter(RedisCounterStore(client=redis), _Clock(1_000.0))

    decision = await limiter.consume("chat", "user-a", limit=2, window_seconds=60)

    assert decision.allowed is False
    assert decision.retry_after_seconds == 12
    script, numkeys, args = redis.calls[0]
    assert isinstance(script, str) and "INCR" in script and "EXPIRE" in script
    assert numkeys == 1
    assert args[0] == "ratelimit:chat:user-a:16"
    assert args[1] == 20


async def test_redis_failure_does_not_expose_the_client_error() -> None:
    redis = _FakeRedis(RedisError("NOAUTH secret-host"))
    store = RedisCounterStore(client=redis)

    with pytest.raises(RateLimitUnavailableError, match="temporarily unavailable") as exc_info:
        await store.increment("ratelimit:chat:user-a:1", 60)

    assert "NOAUTH" not in str(exc_info.value)
    assert "secret-host" not in str(exc_info.value)


async def test_closing_the_limiter_closes_redis() -> None:
    redis = _FakeRedis([1, 60])
    limiter = RateLimiter(RedisCounterStore(client=redis))

    await limiter.aclose()

    assert redis.closed is True


def test_development_without_redis_uses_the_in_process_limiter() -> None:
    app = create_app(make_settings())

    assert app.state.rate_limiter.backend == "memory"


def test_configured_redis_is_selected_without_connecting() -> None:
    app = create_app(make_settings(redis_url="redis://:s3cret@localhost:6379/0"))

    assert app.state.rate_limiter.backend == "redis"
    assert "s3cret" not in repr(app.state.settings)


def test_empty_redis_url_is_unset() -> None:
    assert make_settings(redis_url="  ").redis_url is None


def test_redis_url_must_use_the_redis_scheme() -> None:
    with pytest.raises(ValidationError, match="redis://"):
        make_settings(redis_url="http://localhost:6379/0")


def test_create_rate_limiter_matches_the_url() -> None:
    assert create_rate_limiter(None).backend == "memory"
    assert create_rate_limiter("redis://localhost:6379/0").backend == "redis"


def _chat_app(limit: int) -> tuple[FastAPI, TestClient, FakeLLMProvider]:
    app = create_app(make_settings(chat_rate_limit_requests=limit, chat_rate_limit_window_seconds=60))
    # Start of a 60-second window, so Retry-After is stable.
    clock = _Clock(960.0)
    app.state.rate_limiter = RateLimiter(MemoryCounterStore(clock), clock)
    install_user(app)
    provider = FakeLLMProvider(reply="Hi")
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return app, TestClient(app, raise_server_exceptions=False), provider


def test_chat_under_the_limit_returns_the_json_answer() -> None:
    _, client, provider = _chat_app(2)

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "Hi", "sources": [], "tools_used": []}
    assert len(provider.calls) == 1


def test_chat_over_the_limit_returns_429_and_does_not_call_the_model() -> None:
    _, client, provider = _chat_app(1)
    assert client.post("/api/v1/chat", json={"message": "Hello"}).status_code == 200

    response = client.post("/api/v1/chat", json={"message": "Hello again"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.json()["error"]["message"] == "Too many chat requests. Try again in 60 seconds."
    assert response.headers["retry-after"] == "60"
    assert len(provider.calls) == 1


def test_stream_shares_the_chat_limit_and_fails_before_the_stream_starts() -> None:
    _, client, provider = _chat_app(1)
    assert client.post("/api/v1/chat", json={"message": "Hello"}).status_code == 200

    response = client.post("/api/v1/chat/stream", json={"message": "Hello"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "event:" not in response.text
    assert len(provider.calls) == 1


def test_missing_token_does_not_consume_the_chat_limit() -> None:
    app = create_app(make_settings(chat_rate_limit_requests=1))
    provider = FakeLLMProvider(reply="Hi")
    app.dependency_overrides[get_llm_provider] = lambda: provider
    client = TestClient(app, raise_server_exceptions=False)

    denied = client.post("/api/v1/chat", json={"message": "Hello"})
    install_user(app)
    allowed = client.post("/api/v1/chat", json={"message": "Hello"})

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert len(provider.calls) == 1


def test_each_user_has_a_separate_chat_limit() -> None:
    app, client, provider = _chat_app(1)
    assert client.post("/api/v1/chat", json={"message": "Hello"}).status_code == 200
    other = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        role=UserRole.USER,
        email="bea@example.com",
        name="Bea",
        password_hash="not-used",
    )
    app.dependency_overrides[get_current_user] = lambda: other

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert len(provider.calls) == 2


def test_forbidden_user_does_not_consume_the_chat_limit() -> None:
    app = create_app(make_settings(chat_rate_limit_requests=1))
    clock = _Clock(960.0)
    store = MemoryCounterStore(clock)
    app.state.rate_limiter = RateLimiter(store, clock)
    install_user(app, role=UserRole.ADMIN)
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="Hi")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 403
    assert store._values == {}


def test_redis_outage_blocks_chat_without_calling_the_model() -> None:
    app, client, provider = _chat_app(5)
    app.state.rate_limiter = RateLimiter(RedisCounterStore(client=_FakeRedis(RedisError("connection refused"))))

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "rate_limit_unavailable",
        "message": "Chat is temporarily unavailable. Try again shortly.",
        "details": None,
    }
    assert "connection refused" not in response.text
    assert provider.calls == []
