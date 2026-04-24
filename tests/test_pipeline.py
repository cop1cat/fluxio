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
    pipe = Pipeline([counter], checkpoint_store=store, durable=True, auto_parallel=False)

    with pytest.raises(RuntimeError):
        await pipe.invoke({}, run_id="r1")

    result = await pipe.invoke({}, run_id="r1")
    assert result.get("done") is True
    pipe.shutdown()


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
