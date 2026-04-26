# Durable execution

fluxio can checkpoint state between stages and resume a crashed run from the last checkpoint.

## Enabling durability

```python
from fluxio import Pipeline, InMemoryStore

pipeline = Pipeline(
    nodes=[...],
    checkpoint_store=InMemoryStore(),
    durable=True,
)
```

Before every `CALL` instruction the interpreter saves `ctx.snapshot()` together with the instruction pointer. If the stage raises, the last successful checkpoint is preserved untouched and the exception propagates — `resume=True` will restart from that checkpoint and replay the failing stage cleanly.

## Fresh runs vs resume

The default behaviour is **always fresh**. If a checkpoint exists for the given `run_id`, it is deleted and the run starts from scratch.

To continue from the last checkpoint, pass `resume=True`:

```python
# crash happened here
await pipeline.invoke({"user_id": 42}, run_id="req-1")

# later, or in a retry loop
await pipeline.invoke({}, run_id="req-1", resume=True)
```

If no checkpoint exists for that `run_id`, `KeyError` is raised.

## Pipeline versioning

Each `CompiledPipeline` has a short sha256 `version`. A checkpoint stores the version it was taken against. Resuming on a pipeline with a different version raises `CheckpointVersionError` — code drift should not silently run against stale state.

## Concurrency

`invoke(run_id="x")` with `durable=True` takes a lock for that `run_id`. A second concurrent call with the same id raises `RunIDInUseError`. Different `run_id`s are unconstrained.

## Stores

### `InMemoryStore` (default)

Process-local dict with an `asyncio.Lock`. Perfect for tests and single-process services.

### `RedisStore`

```python
from fluxio import RedisStore

pipeline = Pipeline(
    ...,
    checkpoint_store=RedisStore(
        url="redis://localhost:6379",
        ttl=86400,
        key_prefix="fluxio:checkpoint",
    ),
    durable=True,
)
```

Install with `pip install fluxio[redis]`.

### Custom backends

Implement `CheckpointStore`:

```python
from fluxio.store.base import CheckpointStore, Checkpoint

class PostgresStore(CheckpointStore):
    async def save(self, checkpoint: Checkpoint) -> None: ...
    async def load(self, run_id: str) -> Checkpoint | None: ...
    async def delete(self, run_id: str) -> None: ...
    async def exists(self, run_id: str) -> bool: ...
```

## Replay and diff

```python
# re-run from stored checkpoint
await pipeline.replay("req-1")

# compare two runs key-by-key
delta = await pipeline.diff("req-1", "req-2")
```
