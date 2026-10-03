"""Fixed-window rate limits for chat, sign-in, and registration.

Redis stores one counter per key per window, then deletes it when the window ends.
Conversations, messages, documents, and agent runs stay in PostgreSQL. With no
REDIS_URL, the same counter lives in this process so local development still enforces
the limit.
"""

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_MAX_MEMORY_KEYS = 1024

# One round trip: increment, and start the expiry only on the first hit in the window.
_INCREMENT_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
return {current, ttl}
"""


class RateLimitedError(AppError):
    def __init__(self, retry_after_seconds: int, *, subject: str = "chat requests") -> None:
        wait = max(1, retry_after_seconds)
        unit = "second" if wait == 1 else "seconds"
        super().__init__(
            f"Too many {subject}. Try again in {wait} {unit}.",
            code="rate_limited",
            status_code=429,
            headers={"Retry-After": str(wait)},
        )


class RateLimitUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "Rate limiting is temporarily unavailable. Try again shortly.",
            code="rate_limit_unavailable",
            status_code=503,
        )


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class CounterStore(Protocol):
    async def increment(self, key: str, ttl_seconds: int) -> tuple[int, int]:
        """Return the new count and the seconds until this key expires."""


class _RedisCommands(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...

    async def aclose(self) -> None: ...


class MemoryCounterStore:
    """Fixed-window counter for one process. Used when Redis is not configured."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._values: dict[str, tuple[int, float]] = {}

    async def increment(self, key: str, ttl_seconds: int) -> tuple[int, int]:
        now = self._clock()
        self._prune(now)
        count, expires_at = self._values.get(key, (0, 0.0))
        if now >= expires_at:
            count = 0
            expires_at = now + ttl_seconds
        count += 1
        self._values[key] = (count, expires_at)
        return count, max(1, math.ceil(expires_at - now))

    def _prune(self, now: float) -> None:
        if len(self._values) <= _MAX_MEMORY_KEYS:
            return
        self._values = {key: value for key, value in self._values.items() if value[1] > now}


class RedisCounterStore:
    """Shared fixed-window counter. The client connects on the first check, not at import."""

    def __init__(self, url: str | None = None, client: _RedisCommands | None = None) -> None:
        self._url = url
        self._client = client

    async def increment(self, key: str, ttl_seconds: int) -> tuple[int, int]:
        try:
            raw = await self._connect().eval(_INCREMENT_SCRIPT, 1, key, ttl_seconds)
        except RedisError as exc:
            logger.warning("Rate limit check failed: %s", type(exc).__name__)
            raise RateLimitUnavailableError() from None
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            logger.error("Rate limit check returned an unexpected result")
            raise RateLimitUnavailableError()
        count = int(raw[0])
        ttl = int(raw[1])
        if ttl < 1:
            ttl = ttl_seconds
        return count, ttl

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _connect(self) -> _RedisCommands:
        if self._client is None:
            if self._url is None:
                raise RateLimitUnavailableError()
            self._client = Redis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        return self._client


class RateLimiter:
    def __init__(self, store: CounterStore, clock: Callable[[], float] | None = None) -> None:
        self._store = store
        self._clock = clock or time.time

    @property
    def backend(self) -> str:
        return "redis" if isinstance(self._store, RedisCounterStore) else "memory"

    async def consume(
        self, scope: str, identity: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        now = self._clock()
        window_id = int(now // window_seconds)
        remaining = window_seconds - (now % window_seconds)
        ttl = max(1, math.ceil(remaining))
        key = f"ratelimit:{scope}:{identity}:{window_id}"
        count, key_ttl = await self._store.increment(key, ttl)
        if count <= limit:
            return RateLimitDecision(allowed=True, retry_after_seconds=0)
        return RateLimitDecision(allowed=False, retry_after_seconds=max(1, key_ttl))

    async def aclose(self) -> None:
        close = getattr(self._store, "aclose", None)
        if close is not None:
            await close()


def create_rate_limiter(redis_url: str | None) -> RateLimiter:
    if redis_url is None:
        clock = time.time
        return RateLimiter(MemoryCounterStore(clock), clock)
    return RateLimiter(RedisCounterStore(url=redis_url))
