from fluxio import NodeType, Pipeline, stage


async def test_sync_stage_runs_in_threadpool():
    @stage(node_type=NodeType.SYNC)
    def compute(ctx):
        return ctx.set("y", ctx.get("x") * 2)

    pipe = Pipeline([compute], auto_parallel=False)
    result = await pipe.invoke({"x": 21})
    assert result.get("y") == 42
    pipe.shutdown()


async def test_stream_stage_accumulates():
    @stage(node_type=NodeType.STREAM)
    async def producer(ctx):
        for i in range(3):
            yield i

    pipe = Pipeline([producer], auto_parallel=False)
    result = await pipe.invoke({})
    assert result.get("producer_stream_result") == [0, 1, 2]
    pipe.shutdown()


async def test_error_propagates():
    import pytest

    @stage
    async def bad(ctx):
        raise RuntimeError("kaboom")

    pipe = Pipeline([bad], auto_parallel=False)
    with pytest.raises(RuntimeError):
        await pipe.invoke({})
    pipe.shutdown()
