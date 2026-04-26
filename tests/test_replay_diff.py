"""Tests for Pipeline.replay() / .diff() / version checks / SYNC stages / RateLimit / empty pipeline."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fluxio import (
    CheckpointVersionError,
    InMemoryStore,
    NoCheckpointError,
    Pipeline,
    RateLimitMiddleware,
    stage,
)
from fluxio.runtime.cache import InMemoryCache
from fluxio.runtime.middleware import CacheMiddleware, RetryMiddleware
from fluxio.testing.harness import StepHarness


async def test_replay_continues_from_checkpoint():
    @stage
    async def step1(ctx):
        return ctx.set("a", 1)

    @stage
    async def step2(ctx):
        return ctx.set("b", ctx.get("a", 0) + 1)

    store = InMemoryStore()
    async with Pipeline(
        [step1, step2], checkpoint_store=store, durable=True, auto_parallel=False
    ) as pipe:
        # Seed a checkpoint at the start so replay has something to load
        # (a normal successful invoke would have deleted it).
        from fluxio.store.base import Checkpoint

        await store.save(
            Checkpoint(
                run_id="rr",
                pipeline_version=pipe.version,
                ip=0,
                ctx_snapshot={},
                created_at=0.0,
            )
        )
        replayed = await pipe.replay("rr")
    assert replayed.get("a") == 1
    assert replayed.get("b") == 2


async def test_replay_raises_no_checkpoint_error():
    @stage
    async def s(ctx):
        return ctx

    async with Pipeline(
        [s], checkpoint_store=InMemoryStore(), durable=True, auto_parallel=False
    ) as pipe:
        with pytest.raises(NoCheckpointError):
            await pipe.replay("missing")


async def test_diff_shows_changed_keys():
    from fluxio.store.base import Checkpoint

    @stage
    async def s(ctx):
        return ctx

    store = InMemoryStore()
    async with Pipeline([s], checkpoint_store=store, durable=True, auto_parallel=False) as pipe:
        await store.save(
            Checkpoint(
                run_id="a",
                pipeline_version=pipe.version,
                ip=0,
                ctx_snapshot={"x": 1, "shared": "same"},
                created_at=0.0,
            )
        )
        await store.save(
            Checkpoint(
                run_id="b",
                pipeline_version=pipe.version,
                ip=0,
                ctx_snapshot={"x": 2, "shared": "same"},
                created_at=0.0,
            )
        )
        d = await pipe.diff("a", "b")
    assert d == {"x": {"a": 1, "b": 2}}


async def test_diff_missing_checkpoint_raises_no_checkpoint_error():
    @stage
    async def s(ctx):
        return ctx

    async with Pipeline(
        [s], checkpoint_store=InMemoryStore(), durable=True, auto_parallel=False
    ) as pipe:
        with pytest.raises(NoCheckpointError):
            await pipe.diff("nope-a", "nope-b")


async def test_resume_with_stale_pipeline_version_raises():
    """Regression: resume must refuse a checkpoint whose pipeline_version differs."""
    from fluxio.store.base import Checkpoint

    @stage
    async def s(ctx):
        return ctx

    store = InMemoryStore()
    await store.save(
        Checkpoint(
            run_id="stale",
            pipeline_version="deadbeefcafebabe",
            ip=0,
            ctx_snapshot={},
            created_at=0.0,
        )
    )
    async with Pipeline([s], checkpoint_store=store, durable=True, auto_parallel=False) as pipe:
        with pytest.raises(CheckpointVersionError):
            await pipe.invoke({}, run_id="stale", resume=True)


async def test_sync_stage_runs_in_thread_pool():
    """SYNC @stage must execute in a worker thread, not the event loop thread."""
    main_thread = threading.current_thread().ident
    saw: list[int | None] = []

    @stage
    def blocking(ctx):
        saw.append(threading.current_thread().ident)
        return ctx.set("done", True)

    async with Pipeline([blocking], auto_parallel=False) as pipe:
        result = await pipe.invoke({})
    assert result.get("done") is True
    assert saw[0] is not None
    assert saw[0] != main_thread


async def test_empty_pipeline_returns_initial_ctx():
    async with Pipeline([], auto_parallel=False) as pipe:
        result = await pipe.invoke({"x": 42})
    assert result.get("x") == 42


async def test_rate_limit_throttles():
    """RateLimitMiddleware must space calls so the configured rps is not exceeded."""
    calls: list[float] = []

    @stage
    async def fast(ctx):
        calls.append(time.monotonic())
        return ctx

    h = StepHarness(fast, middleware=[RateLimitMiddleware(rps=2)])
    await asyncio.gather(h.run({}), h.run({}), h.run({}))
    h.close()
    assert len(calls) == 3
    # 3 calls at 2 rps must take at least ~0.5s (the 3rd waits for window).
    assert calls[-1] - calls[0] >= 0.4


async def test_retry_bypasses_stream_stage():
    """RetryMiddleware must NOT retry STREAM stages — duplicate chunks are a contract violation."""
    from fluxio import NodeType

    calls = {"n": 0}

    @stage(node_type=NodeType.STREAM)
    async def streamer(ctx):
        calls["n"] += 1
        yield "chunk"

    h = StepHarness(streamer, middleware=[RetryMiddleware(max_attempts=5, base_delay=0.0)])
    await h.run_stream({})
    h.close()
    assert calls["n"] == 1


async def test_cache_bypasses_stream_stage():
    """CacheMiddleware must NOT cache STREAM stages — caching a live generator is meaningless."""
    from fluxio import NodeType

    calls = {"n": 0}

    @stage(node_type=NodeType.STREAM)
    async def streamer(ctx):
        calls["n"] += 1
        yield "x"

    store = InMemoryCache()
    h = StepHarness(streamer, middleware=[CacheMiddleware(store=store, ttl=60)])
    await h.run_stream({})
    await h.run_stream({})
    h.close()
    assert calls["n"] == 2


def test_all_public_names_resolve():
    """Every entry in fluxio.__all__ must resolve to a real object — guards against typos."""
    import fluxio

    for name in fluxio.__all__:
        assert getattr(fluxio, name, None) is not None, f"fluxio.{name} resolved to None"
