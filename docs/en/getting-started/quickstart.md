# Quickstart

A walk-through of the core moving parts in one file.

```python
import asyncio
from fluxio import Pipeline, Parallel, stage

# 1. Stages — any function decorated with @stage.
@stage
async def fetch_user(ctx):
    return ctx.set("user", {"id": ctx["user_id"], "name": "Alice"})

# 2. Declared reads/writes enable auto-parallelism and conflict detection.
@stage(reads=frozenset({"user"}), writes=frozenset({"profile"}))
async def enrich(ctx):
    return ctx.set("profile", {"bio": "..."})

@stage(reads=frozenset({"user"}), writes=frozenset({"orders"}))
async def fetch_orders(ctx):
    return ctx.set("orders", [1, 2, 3])

@stage
async def finalize(ctx):
    return ctx.set(
        "summary",
        f"{ctx['user']['name']} has {len(ctx['orders'])} orders",
    )

# 3. Compile once, invoke many. async with ensures clean shutdown.
async def main() -> None:
    async with Pipeline(
        [
            fetch_user,
            Parallel([enrich, fetch_orders]),
            finalize,
        ],
    ) as pipe:
        result = await pipe.invoke({"user_id": 42})
        print(result["summary"])  # Alice has 3 orders

asyncio.run(main())
```

## What just happened

1. **`@stage`** attached metadata to each function. Stage type (`ASYNC` / `SYNC` / `STREAM`) was auto-detected from the signature.
2. **`Pipeline(...)`** compiled the nodes into a linear bytecode once.
3. **`pipe.invoke({...})`** ran the program, passing an immutable `Context` from stage to stage.
4. **`Parallel([...])`** ran `enrich` and `fetch_orders` concurrently and merged their writes.
5. **`async with`** closed the thread pool used for `SYNC` stages.

Next: learn the [Stage](../concepts/stage.md), [Context](../concepts/context.md), and [Pipeline](../concepts/pipeline.md) primitives in detail.
