# fluxio

Streamable, durable pipeline runtime for Python backend services.

## Why fluxio

- **Composable stages** — decorate plain functions with `@stage`. Sync, async, and streaming functions are auto-detected.
- **Immutable HAMT context** — every `ctx.set()` returns a new context with structural sharing. Forks are O(1), merges detect write conflicts.
- **Auto-parallelism** — declare `reads` / `writes` and the compiler parallelizes independent stages for you.
- **Durable execution** — checkpoint state between stages, resume after a crash with an explicit `resume=True`.
- **Conditional routing** — return `Send("route-name")` and direct execution through a `dict` block of sub-pipelines.
- **Streaming** — yield chunks from any stage, consume them via `pipe.stream()` or `on_step_stream` callbacks.
- **Batteries included** — retry, cache, circuit breaker, rate limit middlewares; logging and Langfuse callbacks; in-memory and Redis stores.

## 30-second example

```python
from fluxio import Pipeline, stage

@stage
async def fetch_user(ctx):
    return ctx.set("user", {"id": ctx["user_id"], "name": "Alice"})

@stage
async def greet(ctx):
    return ctx.set("greeting", f"Hello {ctx['user']['name']}")

async with Pipeline([fetch_user, greet]) as pipe:
    result = await pipe.invoke({"user_id": 1})
    print(result["greeting"])
```

## Where to go next

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [Concepts: Stage](concepts/stage.md) — the unit of composition
- [Guides: Durable execution](guides/durable.md) — crash-resilient pipelines
- [API reference](reference/api.md)
