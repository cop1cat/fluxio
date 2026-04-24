import pytest

from fluxio import (
    CacheMiddleware,
    CircuitBreakerMiddleware,
    CircuitOpenError,
    RetryMiddleware,
    stage,
)
from fluxio.runtime.cache import InMemoryCache
from fluxio.testing.harness import StepHarness


async def test_retry_success_after_failures():
    attempts = {"n": 0}

    @stage
    async def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("fail")
        return ctx.set("ok", True)

    h = StepHarness(flaky, middleware=[RetryMiddleware(max_attempts=3, base_delay=0.0)])
    result = await h.run({})
    assert result.get("ok") is True
    assert attempts["n"] == 3
    h.close()


async def test_retry_exhausts():
    @stage
    async def bad(ctx):
        raise ValueError("nope")

    h = StepHarness(bad, middleware=[RetryMiddleware(max_attempts=2, base_delay=0.0)])
    with pytest.raises(ValueError):
        await h.run({})
    h.close()


async def test_cache_hits_skip_call():
    calls = {"n": 0}

    @stage
    async def expensive(ctx):
        calls["n"] += 1
        return ctx.set("result", ctx.get("x") * 2)

    store = InMemoryCache()
    h = StepHarness(expensive, middleware=[CacheMiddleware(store=store, ttl=60)])
    r1 = await h.run({"x": 5})
    r2 = await h.run({"x": 5})
    assert r1.get("result") == 10
    assert r2.get("result") == 10
    assert calls["n"] == 1
    h.close()


async def test_circuit_breaker_opens():
    @stage
    async def bad(ctx):
        raise ValueError("fail")

    cb = CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=60)
    h = StepHarness(bad, middleware=[cb])
    for _ in range(2):
        with pytest.raises(ValueError):
            await h.run({})
    with pytest.raises(CircuitOpenError):
        await h.run({})
    h.close()
