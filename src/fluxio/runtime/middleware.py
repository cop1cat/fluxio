from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
import hashlib
import json
import logging
import random
import time
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from fluxio.api.primitives import StageFunc
    from fluxio.context.context import Context
    from fluxio.runtime.cache import CacheStore

_logger = logging.getLogger("fluxio.middleware")

Next = Callable[["StageFunc", "Context"], Awaitable["Context"]]


def _is_stream(fn: object) -> bool:
    from fluxio.api.primitives import NodeType

    return getattr(fn, "__fluxio_node_type__", None) == NodeType.STREAM


class Middleware(ABC):
    @abstractmethod
    async def __call__(
        self,
        fn: StageFunc,
        ctx: Context,
        next: Next,
    ) -> Context: ...


class MiddlewareChain:
    def __init__(self, middlewares: list[Middleware]) -> None:
        self._middlewares = list(middlewares)

    async def run(
        self,
        fn: StageFunc,
        ctx: Context,
        terminal: Next,
    ) -> Context:
        chain: Next = terminal
        for mw in reversed(self._middlewares):
            chain = self._wrap(mw, chain)
        return await chain(fn, ctx)

    @staticmethod
    def _wrap(mw: Middleware, nxt: Next) -> Next:
        async def run(fn: StageFunc, ctx: Context) -> Context:
            return await mw(fn, ctx, nxt)

        return run


class RetryMiddleware(Middleware):
    """Retries the stage up to ``max_attempts`` times on matching exceptions.

    Bypassed for STREAM stages — partial chunks are already delivered on the
    first attempt, so retrying would produce duplicate output.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        backoff: Literal["fixed", "exponential", "jitter"] = "exponential",
        base_delay: float = 0.5,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.base_delay = base_delay
        self.exceptions = exceptions

    async def __call__(self, fn: StageFunc, ctx: Context, next: Next) -> Context:
        if _is_stream(fn):
            return await next(fn, ctx)
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await next(fn, ctx)
            except self.exceptions as e:
                last = e
                _logger.warning(
                    "retry attempt=%d/%d stage=%s error=%s",
                    attempt,
                    self.max_attempts,
                    getattr(fn, "__name__", "?"),
                    e,
                )
                if attempt == self.max_attempts:
                    break
                await asyncio.sleep(self._delay(attempt))
        assert last is not None
        raise last

    def _delay(self, attempt: int) -> float:
        if self.backoff == "fixed":
            return self.base_delay
        if self.backoff == "exponential":
            return self.base_delay * (2 ** (attempt - 1))
        return self.base_delay * (2 ** (attempt - 1)) * random.uniform(0.5, 1.5)


class CacheMiddleware(Middleware):
    """Memoizes stage output in a ``CacheStore`` keyed by stage name + ctx hash.

    Defaults to an in-process ``InMemoryCache``. Bypassed for STREAM stages.
    """

    def __init__(
        self,
        store: CacheStore | None = None,
        ttl: int = 300,
        key_fn: Callable[[StageFunc, Context], str] | None = None,
    ) -> None:
        from fluxio.runtime.cache import InMemoryCache

        self.store: CacheStore = store or InMemoryCache()
        self.ttl = ttl
        self.key_fn = key_fn

    async def __call__(self, fn: StageFunc, ctx: Context, next: Next) -> Context:
        if _is_stream(fn):
            return await next(fn, ctx)

        from fluxio.context.context import Context as _Ctx
        from fluxio.runtime.cache import CacheEntry

        key = self._build_key(fn, ctx)
        existing = await self.store.get(key)
        now = time.time()
        if existing and (now - existing.created_at) < self.ttl:
            _logger.debug("cache hit stage=%s", getattr(fn, "__name__", "?"))
            return _Ctx.from_snapshot(
                existing.value,
                name=ctx.name,
                written=frozenset(existing.written),
            )

        result = await next(fn, ctx)
        await self.store.set(
            key,
            CacheEntry(
                value=result.snapshot(),
                created_at=now,
                written=tuple(result._written),
            ),
        )
        return result

    def _build_key(self, fn: StageFunc, ctx: Context) -> str:
        if self.key_fn is not None:
            return self.key_fn(fn, ctx)
        node_id = getattr(fn, "__name__", "?")
        try:
            payload = json.dumps(ctx.snapshot(), default=str, sort_keys=True)
        except (TypeError, ValueError):
            payload = repr(ctx.snapshot())
        digest = hashlib.sha256((node_id + "|" + payload).encode()).hexdigest()
        return f"cache:{node_id}:{digest}"


class CircuitOpenError(Exception):
    pass


class CircuitBreakerMiddleware(Middleware):
    """Opens the circuit after ``failure_threshold`` consecutive failures.

    In the OPEN state ``CircuitOpenError`` is raised immediately without
    calling the stage, until ``recovery_timeout`` elapses.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.exceptions = exceptions
        self._failures = 0
        self._state: Literal["closed", "open", "half_open"] = "closed"
        self._opened_at: float | None = None
        self._probing = False
        self._lock = asyncio.Lock()

    async def __call__(self, fn: StageFunc, ctx: Context, next: Next) -> Context:
        # Track whether THIS call is the half-open probe. Only the probe
        # closes/re-opens the circuit; concurrent callers see the breaker
        # as still open and bail out fast.
        is_probe = False
        async with self._lock:
            if self._state == "open":
                assert self._opened_at is not None
                if (
                    time.monotonic() - self._opened_at >= self.recovery_timeout
                    and not self._probing
                ):
                    self._state = "half_open"
                    self._probing = True
                    is_probe = True
                else:
                    raise CircuitOpenError(f"Circuit open for stage {getattr(fn, '__name__', '?')}")
            elif self._state == "half_open" and not self._probing:
                self._probing = True
                is_probe = True
            elif self._state == "half_open":
                raise CircuitOpenError(
                    f"Circuit half-open probe in flight for stage {getattr(fn, '__name__', '?')}"
                )
        try:
            result = await next(fn, ctx)
        except self.exceptions:
            async with self._lock:
                if is_probe:
                    self._probing = False
                    self._state = "open"
                    self._opened_at = time.monotonic()
                else:
                    self._failures += 1
                    if self._failures >= self.failure_threshold:
                        self._state = "open"
                        self._opened_at = time.monotonic()
            raise
        async with self._lock:
            if is_probe:
                self._probing = False
            self._failures = 0
            self._state = "closed"
            self._opened_at = None
        return result


class RateLimitMiddleware(Middleware):
    """Token-bucket style sliding-window rate limit. Waits, never raises."""

    def __init__(self, rps: float) -> None:
        if rps <= 0:
            raise ValueError("rps must be positive")
        self.rps = rps
        self._window: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def __call__(self, fn: StageFunc, ctx: Context, next: Next) -> Context:
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._window and now - self._window[0] >= 1.0:
                    self._window.popleft()
                if len(self._window) < self.rps:
                    self._window.append(now)
                    break
                wait = 1.0 - (now - self._window[0])
            await asyncio.sleep(max(wait, 0.001))
        return await next(fn, ctx)


__all__ = [
    "CacheMiddleware",
    "CircuitBreakerMiddleware",
    "CircuitOpenError",
    "Middleware",
    "MiddlewareChain",
    "Next",
    "RateLimitMiddleware",
    "RetryMiddleware",
]
