import asyncio

import pytest

from fluxio import BaseCallback, Pipeline, Send, stage


async def test_async_context_manager_shutdowns():
    @stage
    async def noop(ctx):
        return ctx

    async with Pipeline([noop], auto_parallel=False) as pipe:
        await pipe.invoke({})


async def test_stage_timeout_raises():
    @stage(timeout=0.05)
    async def slow(ctx):
        await asyncio.sleep(1.0)
        return ctx

    async with Pipeline([slow], auto_parallel=False) as pipe:
        with pytest.raises(TimeoutError):
            await pipe.invoke({})


async def test_stage_timeout_ok_under_budget():
    @stage(timeout=1.0)
    async def quick(ctx):
        await asyncio.sleep(0.01)
        return ctx.set("done", True)

    async with Pipeline([quick], auto_parallel=False) as pipe:
        result = await pipe.invoke({})
    assert result.get("done") is True


async def test_on_route_called_with_choice():
    seen: list[tuple[str, str]] = []

    class RouteSpy(BaseCallback):
        async def on_route(self, run_id, step, route):
            seen.append((step, route))

    @stage
    async def router(ctx):
        return Send("a", {"chose": "a"})

    @stage
    async def leaf_a(ctx):
        return ctx.set("leaf", "a")

    @stage
    async def leaf_b(ctx):
        return ctx.set("leaf", "b")

    async with Pipeline(
        [router, {"a": [leaf_a], "b": [leaf_b]}],
        callbacks=[RouteSpy()],
        auto_parallel=False,
    ) as pipe:
        await pipe.invoke({})
    assert seen == [("router", "a")]


async def test_stream_yields_chunks_only():
    @stage
    async def producer(ctx):
        for i in range(3):
            yield i

    async with Pipeline([producer], auto_parallel=False) as pipe:
        got = [c async for c in pipe.stream({})]
    assert got == [0, 1, 2]


async def test_concurrent_streams_do_not_mix():
    @stage
    async def producer(ctx):
        for i in range(ctx["n"]):
            yield i

    async with Pipeline([producer], auto_parallel=False) as pipe:

        async def collect(n: int) -> list[int]:
            return [c async for c in pipe.stream({"n": n})]

        a, b = await asyncio.gather(collect(3), collect(5))
    assert a == [0, 1, 2]
    assert b == [0, 1, 2, 3, 4]
