# Conditional routing

Branch the pipeline at runtime based on data.

## Basics

```python
from fluxio import Pipeline, Send, stage

@stage
async def classify(ctx):
    tier = "premium" if ctx["user"]["plan"] == "pro" else "standard"
    return ctx.set("tier", tier)

@stage
async def router(ctx):
    if ctx["tier"] == "premium":
        return Send("premium", {"priority": "high"})
    return Send("standard")

@stage
async def fast_llm(ctx): return ctx.set("answer", "fast")

@stage
async def cheap_llm(ctx): return ctx.set("answer", "cheap")

@stage
async def finalize(ctx): return ctx.set("done", True)

pipeline = Pipeline([
    classify,
    router,
    {
        "premium":  [fast_llm],
        "standard": [cheap_llm],
    },
    finalize,
])
```

`router` returns `Send("premium", patch={...})`. The dict following the router selects which sub-pipeline to run. The `patch` is applied to the context before the selected branch executes. After the branch completes, execution continues with the next top-level node (`finalize`).

## Route bodies

A dict value can be:

- a list of stages
- a single stage
- a `Pipeline` instance (its nodes are unpacked)

```python
{
    "premium":  Pipeline([fast_llm, priority_queue]),
    "standard": [cheap_llm, normal_queue],
}
```

## Tracing

Add `on_route` in a callback to observe decisions:

```python
class Spy(BaseCallback):
    async def on_route(self, run_id, step, route):
        metrics.incr(f"route.{step}.{route}")
```

## Nested routing

Dicts can be nested arbitrarily: put another `router → dict` pair inside a route body. Each dict must follow a stage that returns `Send` — the compiler enforces this.
