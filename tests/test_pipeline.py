import pytest

from fluxio import InMemoryStore, Parallel, Pipeline, stage


@stage
async def fetch(ctx):
    return ctx.set("user", {"id": ctx.get("user_id"), "name": "Alice"})


@stage
async def greet(ctx):
    return ctx.set("greeting", f"Hello {ctx.get('user')['name']}")


async def test_invoke_linear():
    pipe = Pipeline([fetch, greet], auto_parallel=False)
    result = await pipe.invoke({"user_id": 1})
    assert result.get("greeting") == "Hello Alice"
    pipe.shutdown()


async def test_invoke_parallel():
    @stage(reads=frozenset({"x"}), writes=frozenset({"a"}))
    async def sa(ctx):
        return ctx.set("a", ctx.get("x") + 1)

    @stage(reads=frozenset({"x"}), writes=frozenset({"b"}))
    async def sb(ctx):
        return ctx.set("b", ctx.get("x") + 2)

    pipe = Pipeline([Parallel([sa, sb])], auto_parallel=False)
    result = await pipe.invoke({"x": 10})
    assert result.get("a") == 11
    assert result.get("b") == 12
    pipe.shutdown()


async def test_durable_resume():
    call_count = {"n": 0}

    @stage
    async def counter(ctx):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return ctx.set("done", True)

    store = InMemoryStore()
    async with Pipeline(
        [counter], checkpoint_store=store, durable=True, auto_parallel=False
    ) as pipe:
        with pytest.raises(RuntimeError):
            await pipe.invoke({}, run_id="r1")

        result = await pipe.invoke({}, run_id="r1", resume=True)
        assert result.get("done") is True


async def test_invoke_without_resume_starts_fresh():
    @stage
    async def succeed(ctx):
        return ctx.set("x", 1)

    store = InMemoryStore()
    async with Pipeline(
        [succeed], checkpoint_store=store, durable=True, auto_parallel=False
    ) as pipe:
        await pipe.invoke({}, run_id="r2")
        result = await pipe.invoke({"x": 99}, run_id="r2")
        assert result.get("x") == 1


async def test_resume_without_checkpoint_raises():
    @stage
    async def noop(ctx):
        return ctx

    store = InMemoryStore()
    async with Pipeline([noop], checkpoint_store=store, durable=True, auto_parallel=False) as pipe:
        with pytest.raises(KeyError):
            await pipe.invoke({}, run_id="missing", resume=True)


async def test_run_step_isolated():
    pipe = Pipeline([fetch, greet], auto_parallel=False)
    out = await pipe.run_step("fetch", {"user_id": 42})
    assert out.get("user")["id"] == 42
    pipe.shutdown()


async def test_explain_includes_version():
    pipe = Pipeline([fetch], auto_parallel=False)
    text = pipe.explain()
    assert "Pipeline" in text
    assert "fetch" in text
    pipe.shutdown()


async def test_parallel_branch_runs_input_schema():
    """Regression: input_schema declared on a stage must validate even when stage runs as a Parallel branch."""
    from pydantic import BaseModel
    import pytest

    from fluxio import Parallel, Pipeline, stage

    class NeedsX(BaseModel):
        x: int

    @stage(input_schema=NeedsX)
    async def needs_x(ctx):
        return ctx.set("x_seen", ctx["x"])

    @stage
    async def other(ctx):
        return ctx.set("y", 1)

    pipe = Pipeline([Parallel([needs_x, other])], auto_parallel=False)
    # x missing → branch input validation must fail
    with pytest.raises(RuntimeError, match="Input validation failed"):
        await pipe.invoke({})
    pipe.shutdown()
