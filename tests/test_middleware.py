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


async def test_cached_branch_writes_survive_merge():
    """A cached stage's writes must merge correctly when used as a Parallel branch.

    Regression: ``CacheMiddleware`` previously restored cached results via
    ``Context.from_snapshot`` with an empty ``_written``, so ``Context.merge``
    silently dropped every key the cached stage produced.
    """
    from fluxio import Context

    @stage
    async def producer(ctx):
        return ctx.set("k", "v")

    store = InMemoryCache()
    h = StepHarness(producer, middleware=[CacheMiddleware(store=store, ttl=60)])
    base = Context.create({"seed": 1}, name="root")
    branch_in = base.fork("b")
    branch_out_first = await h.run(branch_in)
    branch_out_cached = await h.run(branch_in)
    merged_first = Context.merge(base, [branch_out_first])
    merged_cached = Context.merge(base, [branch_out_cached])
    assert merged_first["k"] == "v"
    assert merged_cached["k"] == "v"
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


async def test_circuit_breaker_half_open_admits_single_probe():
    """Regression: half_open must admit exactly one probe at a time, not flood."""
    import asyncio

    from fluxio import CircuitBreakerMiddleware, CircuitOpenError, stage

    @stage
    async def slow(ctx):
        await asyncio.sleep(0.05)
        return ctx

    cb = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=0.0)
    # Force OPEN.
    cb._state = "open"
    cb._opened_at = 0.0  # in the past → recovery_timeout elapsed
    h = StepHarness(slow, middleware=[cb])

    # First call: becomes the half-open probe.
    probe = asyncio.create_task(h.run({}))
    await asyncio.sleep(0)  # let probe enter the lock

    # Concurrent caller during the probe: must be rejected fast.
    with pytest.raises(CircuitOpenError):
        await h.run({})

    await probe
    h.close()
