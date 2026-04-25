from fluxio import Pipeline, Send, stage


@stage
async def classify(ctx):
    return ctx.set("tier", ctx.get("input_tier"))


@stage
async def router(ctx):
    if ctx.get("tier") == "premium":
        return Send("premium", {"priority": "high"})
    return Send("standard", {"priority": "normal"})


@stage
async def fast_llm(ctx):
    return ctx.set("result", "fast")


@stage
async def cheap_llm(ctx):
    return ctx.set("result", "cheap")


@stage
async def finalize(ctx):
    return ctx.set("final", ctx.get("result"))


async def test_route_premium():
    pipe = Pipeline(
        [
            classify,
            router,
            {"premium": [fast_llm], "standard": [cheap_llm]},
            finalize,
        ],
        auto_parallel=False,
    )
    result = await pipe.invoke({"input_tier": "premium"})
    assert result.get("result") == "fast"
    assert result.get("priority") == "high"
    assert result.get("final") == "fast"
    pipe.shutdown()


async def test_route_standard():
    pipe = Pipeline(
        [
            classify,
            router,
            {"premium": [fast_llm], "standard": [cheap_llm]},
            finalize,
        ],
        auto_parallel=False,
    )
    result = await pipe.invoke({"input_tier": "basic"})
    assert result.get("result") == "cheap"
    assert result.get("priority") == "normal"
    assert result.get("final") == "cheap"
    pipe.shutdown()


async def test_route_accepts_pipeline_value():
    sub = Pipeline([fast_llm], auto_parallel=False)
    pipe = Pipeline(
        [
            classify,
            router,
            {"premium": sub, "standard": [cheap_llm]},
        ],
        auto_parallel=False,
    )
    result = await pipe.invoke({"input_tier": "premium"})
    assert result.get("result") == "fast"
    pipe.shutdown()
    sub.shutdown()
