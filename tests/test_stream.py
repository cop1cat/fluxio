"""Tests for pipe.stream() — yielding chunks, early exit, durable lock, zero chunks."""

from __future__ import annotations

import asyncio

import pytest

from fluxio import (
    InMemoryStore,
    NodeType,
    Pipeline,
    RunIDInUseError,
    stage,
)


async def test_stream_yields_chunks():
    @stage(node_type=NodeType.STREAM)
    async def gen(ctx):
        for i in range(3):
            yield i

    async with Pipeline([gen], auto_parallel=False) as pipe:
        chunks = [c async for c in pipe.stream({})]
    assert chunks == [0, 1, 2]


async def test_stream_zero_chunks_completes():
    """A pipeline with no STREAM stages must complete the stream() generator cleanly."""

    @stage
    async def noop(ctx):
        return ctx.set("done", True)

    async with Pipeline([noop], auto_parallel=False) as pipe:
        chunks = [c async for c in pipe.stream({})]
    assert chunks == []


async def test_stream_early_break_does_not_hang():
    """Breaking out of the consumer loop must cancel the producer and not hang."""
    produced: list[int] = []

    @stage(node_type=NodeType.STREAM)
    async def slow_gen(ctx):
        for i in range(100):
            produced.append(i)
            await asyncio.sleep(0.005)
            yield i

    async with Pipeline([slow_gen], auto_parallel=False) as pipe:
        first = None
        async for c in pipe.stream({}):
            first = c
            break

    assert first == 0
    assert len(produced) < 50  # producer did not run to completion


async def test_stream_holds_run_id_lock_for_durable():
    """Concurrent stream + invoke on the same durable run_id must reject the second one."""

    @stage(node_type=NodeType.STREAM)
    async def slow_gen(ctx):
        for i in range(3):
            await asyncio.sleep(0.05)
            yield i

    async with Pipeline(
        [slow_gen], checkpoint_store=InMemoryStore(), durable=True, auto_parallel=False
    ) as pipe:

        async def consume_stream():
            return [c async for c in pipe.stream({}, run_id="dup")]

        task = asyncio.create_task(consume_stream())
        await asyncio.sleep(0.01)  # let stream enter the lock
        with pytest.raises(RunIDInUseError):
            await pipe.invoke({}, run_id="dup")
        await task
