# Pipeline

`Pipeline` compiles a list of stages, `Parallel` blocks, and routing dicts into executable bytecode and orchestrates runs.

## Construction

```python
async with Pipeline(
    nodes=[stage_a, stage_b, Parallel([c, d]), router, {"x": [e], "y": [f]}],
    middleware=[RetryMiddleware(), CacheMiddleware()],
    callbacks=[LoggingCallback()],
    checkpoint_store=InMemoryStore(),
    durable=True,
    max_workers=8,
    auto_parallel=True,
) as pipe:
    ...
```

- Compilation happens **once**, in `__init__`. The result is cached in `pipe.version` (a short sha256).
- `async with` is the recommended form — it closes the internal thread pool on exit.

## Running

### `invoke`

```python
result: Context = await pipe.invoke({"user_id": 42})
```

With durable execution:

```python
# first attempt crashes somewhere mid-pipeline
await pipe.invoke({"user_id": 42}, run_id="req-1")

# resume from last checkpoint
await pipe.invoke({}, run_id="req-1", resume=True)
```

### `stream`

Yields chunks from STREAM stages as they arrive:

```python
async with Pipeline([ingest, llm_stream]) as pipe:
    async for chunk in pipe.stream({"prompt": "hi"}):
        await websocket.send(chunk)
```

### `run_step`

Runs a single stage in isolation — useful for tests:

```python
out = await pipe.run_step("fetch_user", {"user_id": 1})
```

### `replay`

Re-runs a pipeline from a stored checkpoint. Requires a configured `checkpoint_store` (passing `durable=True` is sufficient — replay forces durable mode internally):

```python
await pipe.replay("req-1")
```

### `explain`

Human-readable structure of the compiled pipeline, including routes and parallel blocks:

```python
print(pipe.explain())
```

## Key guarantees

- Concurrent `invoke(run_id="x")` with `durable=True` on the same pipeline raises `RunIDInUseError`.
- `STREAM` stages bypass `RetryMiddleware` and `CacheMiddleware` automatically — partial chunks have already been delivered.
- `async with` is safe to omit for purely-async pipelines, but you must then call `pipe.shutdown()` manually.
