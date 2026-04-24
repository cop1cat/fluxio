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
    from fluxio.store.base import CheckpointStore

_logger = logging.getLogger("fluxio.middleware")

Next = Callable[["StageFunc", "Context"], Awaitable["Context"]]


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
    def __init__(
        self,
        store: CheckpointStore,
        ttl: int = 300,
        key_fn: Callable[[StageFunc, Context], str] | None = None,
    ) -> None:
        self.store = store
        self.ttl = ttl
        self.key_fn = key_fn

    async def __call__(self, fn: StageFunc, ctx: Context, next: Next) -> Context:
        from fluxio.context.context import Context as _Ctx
        from fluxio.store.base import Checkpoint

        key = self._build_key(fn, ctx)
        existing = await self.store.load(key)
        now = time.time()
        if existing and not existing.error and (now - existing.created_at) < self.ttl:
            _logger.debug("cache hit stage=%s", getattr(fn, "__name__", "?"))
            return _Ctx.from_snapshot(existing.ctx_snapshot, name=ctx.name)

        result = await next(fn, ctx)
        snap = result.snapshot()
        await self.store.save(
            Checkpoint(
                run_id=key,
                pipeline_version="cache",
                ip=0,
                ctx_snapshot=snap,
                created_at=now,
            )
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
        self._lock = asyncio.Lock()

    async def __call__(self, fn: StageFunc, ctx: Context, next: Next) -> Context:
        async with self._lock:
            if self._state == "open":
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = "half_open"
                else:
                    raise CircuitOpenError(f"Circuit open for stage {getattr(fn, '__name__', '?')}")
        try:
            result = await next(fn, ctx)
        except self.exceptions:
            async with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._state = "open"
                    self._opened_at = time.monotonic()
            raise
        async with self._lock:
            self._failures = 0
            self._state = "closed"
            self._opened_at = None
        return result


class RateLimitMiddleware(Middleware):
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
