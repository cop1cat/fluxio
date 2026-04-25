import asyncio

import pytest

from fluxio import (
    BaseCallback,
    CheckpointVersionError,
    InMemoryStore,
    Pipeline,
    Send,
    stage,
)


async def test_stream_consumer_break_cancels_driver():
    """Breaking out of `pipe.stream(...)` must not leak the driver task."""
    produced: list[int] = []

    @stage
    async def slow_stream(ctx):
        for i in range(100):
            produced.append(i)
            await asyncio.sleep(0.01)
            yield i

    async with Pipeline([slow_stream], auto_parallel=False) as pipe:
        async for chunk in pipe.stream({}):
            if chunk == 2:
                break
        await asyncio.sleep(0.05)

    assert len(produced) < 50


async def test_resume_replays_step_start_and_validation():
    """After a crash, resume must replay the failing step, including step_start."""
    from pydantic import BaseModel

    class S(BaseModel):
        flag: bool

    starts: list[str] = []
    validated: list[str] = []

    class Tap(BaseCallback):
        async def on_step_start(self, run_id, step, ctx):
            starts.append(step)

    attempts = {"n": 0}

    @stage(input_schema=S)
    async def checker(ctx):
        validated.append("yes")
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("boom")
        return ctx.set("done", True)

    async with Pipeline(
        [checker],
        callbacks=[Tap()],
        checkpoint_store=InMemoryStore(),
        durable=True,
        auto_parallel=False,
    ) as pipe:
        with pytest.raises(RuntimeError):
            await pipe.invoke({"flag": True}, run_id="r")
        result = await pipe.invoke({}, run_id="r", resume=True)

    assert result.get("done") is True
    assert starts == ["checker", "checker"]
    assert len(validated) == 2


async def test_run_id_lock_is_race_free():
    """Concurrent invokes with the same run_id: only one proceeds, others raise."""
    from fluxio import RunIDInUseError

    @stage
    async def slow(ctx):
        await asyncio.sleep(0.05)
        return ctx.set("ok", True)

    async with Pipeline(
        [slow],
        checkpoint_store=InMemoryStore(),
        durable=True,
        auto_parallel=False,
    ) as pipe:
        results = await asyncio.gather(
            *(pipe.invoke({}, run_id="r") for _ in range(5)),
            return_exceptions=True,
        )

    successes = [r for r in results if not isinstance(r, BaseException)]
    conflicts = [r for r in results if isinstance(r, RunIDInUseError)]
    assert len(successes) == 1
    assert len(conflicts) == 4


async def test_auto_parallel_preserves_router_dict_adjacency():
    """Router stage must not be folded into a Parallel with its neighbour."""

    @stage(reads=frozenset({"k"}), writes=frozenset({"a"}))
    async def preamble(ctx):
        return ctx.set("a", 1)

    @stage(reads=frozenset({"k"}), writes=frozenset({"chose"}))
    async def router(ctx):
        return Send("x", {"chose": "x"})

    @stage
    async def leaf(ctx):
        return ctx.set("leaf", True)

    async with Pipeline(
        [preamble, router, {"x": [leaf]}],
        auto_parallel=True,
    ) as pipe:
        result = await pipe.invoke({"k": 1})

    assert result.get("a") == 1
    assert result.get("chose") == "x"
    assert result.get("leaf") is True


async def test_pipeline_end_duration_is_measured():
    """on_pipeline_end must receive a non-zero elapsed duration."""
    durations: list[int] = []

    class Timer(BaseCallback):
        async def on_pipeline_end(self, run_id, ctx, duration_ms):
            durations.append(duration_ms)

    @stage
    async def sleep_a_bit(ctx):
        await asyncio.sleep(0.05)
        return ctx

    async with Pipeline([sleep_a_bit], callbacks=[Timer()], auto_parallel=False) as pipe:
        await pipe.invoke({})

    assert len(durations) == 1
    assert durations[0] >= 40


def test_checkpoint_version_error_is_public():
    assert CheckpointVersionError is not None


async def test_step_harness_context_manager_closes():
    from fluxio.testing.harness import StepHarness

    @stage
    async def s(ctx):
        return ctx.set("x", 1)

    with StepHarness(s) as h:
        result = await h.run({})
    assert result.get("x") == 1
    assert h._thread_pool._shutdown is True
