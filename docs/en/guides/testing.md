# Testing

fluxio ships small helpers for unit-testing pipelines and stages.

## `make_ctx`

```python
from fluxio.testing.fixtures import make_ctx

ctx = make_ctx({"user_id": 1})
assert ctx["user_id"] == 1
```

## `StepHarness`

Run a single stage in isolation with optional middleware:

```python
from fluxio.testing.harness import StepHarness
from fluxio import RetryMiddleware

async def test_fetch_user_retries():
    harness = StepHarness(
        fetch_user,
        middleware=[RetryMiddleware(max_attempts=3, base_delay=0.0)],
    )
    try:
        result = await harness.run({"user_id": 1})
        assert result["user"]["name"] == "Alice"
    finally:
        harness.close()
```

`StepHarness.run_stream(ctx)` collects all chunks a STREAM stage yields into a list.

### Asserting writes

```python
ctx_before = make_ctx({"user": fake_user})
ctx_after = await harness.run(ctx_before)
harness.assert_writes(ctx_before, ctx_after, keys={"profile"})
```

Ensures the stage wrote exactly the expected keys — no more, no less.

## Running the full pipeline

In integration tests, use `async with Pipeline(...)` inside an `async def test_...`:

```python
async def test_full_flow():
    async with Pipeline([fetch_user, enrich, finalize]) as pipe:
        result = await pipe.invoke({"user_id": 1})
    assert result["summary"].startswith("Alice")
```

## Tips

- Use `auto_parallel=False` in tests when you want a deterministic execution order.
- For checkpoint behaviour, use `InMemoryStore()` explicitly — it's deterministic and isolated per test.
- Mock external dependencies at the stage boundary: wrap network calls in a stage and substitute via fixtures.
