# Stage

A **stage** is the unit of composition in fluxio. It is any function decorated with `@stage` that takes a `Context` and returns a `Context` (or `Send`, for routing).

## Three flavours, one decorator

Stage type is auto-detected from the function signature:

=== "ASYNC"

    ```python
    @stage
    async def fetch_user(ctx):
        return ctx.set("user", await db.get(ctx["user_id"]))
    ```

=== "SYNC"

    ```python
    @stage
    def compute_hash(ctx):
        return ctx.set("hash", hashlib.sha256(ctx["blob"]).hexdigest())
    ```

    SYNC stages run in a thread pool, so CPU-bound work doesn't block the event loop.

=== "STREAM"

    ```python
    @stage
    async def llm_stream(ctx):
        async for chunk in llm.stream(ctx["prompt"]):
            yield chunk
    ```

    Any `async def` generator becomes a STREAM stage. Chunks are delivered via `pipe.stream()` and the full list is also stored in `ctx[f"{node_id}_stream_result"]`.

## Declared reads and writes

```python
@stage(reads=frozenset({"user_id"}), writes=frozenset({"user"}))
async def fetch_user(ctx): ...
```

Declaring `reads` / `writes` unlocks two features:

- **Auto-parallelism.** Consecutive stages with disjoint dependencies are wrapped in an implicit `Parallel([...])` block at compile time.
- **Write-conflict detection.** If two branches of a `Parallel` write the same key, compilation fails with `CompilationError`.

## Per-stage options

```python
from pydantic import BaseModel

class UserInput(BaseModel):
    user_id: int

@stage(
    input_schema=UserInput,      # validates before CALL
    output_schema=UserOutput,    # validates after CALL
    timeout=5.0,                 # asyncio.timeout around the call
)
async def fetch_user(ctx): ...
```

Schemas are validated against `ctx.snapshot()`. Extra keys are ignored — schemas describe what a stage requires / produces, not the entire world.

## Returning `Send` for routing

```python
from fluxio import Send

@stage
async def route(ctx):
    if ctx["tier"] == "premium":
        return Send("premium", {"priority": "high"})
    return Send("standard")
```

See [Conditional routing](../guides/routing.md).
