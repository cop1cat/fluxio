# Middleware

Middlewares wrap every stage invocation. They are applied in declaration order — outermost first:

```python
Pipeline(
    [...],
    middleware=[
        CircuitBreakerMiddleware(),   # outermost
        RetryMiddleware(),            # inside breaker
        CacheMiddleware(),            # closest to the stage
    ],
)
# Call order: CircuitBreaker → Retry → Cache → stage
```

## Built-in middlewares

### `RetryMiddleware`

```python
RetryMiddleware(
    max_attempts=3,
    backoff="exponential",   # "fixed" | "exponential" | "jitter"
    base_delay=0.5,
    exceptions=(Exception,),
)
```

Bypassed for STREAM stages (retrying would duplicate emitted chunks).

### `CacheMiddleware`

```python
CacheMiddleware(
    store=InMemoryCache(),   # or a custom CacheStore
    ttl=300,
    key_fn=None,             # defaults to sha256(node_id + ctx_snapshot)
)
```

Uses a dedicated `CacheStore` interface — keeps cache keyspace separate from checkpoint storage. Bypassed for STREAM stages.

### `CircuitBreakerMiddleware`

```python
CircuitBreakerMiddleware(
    failure_threshold=5,
    recovery_timeout=60.0,
)
```

States: `closed → open → half_open`. In `open` state, `CircuitOpenError` is raised immediately.

### `RateLimitMiddleware`

```python
RateLimitMiddleware(rps=10.0)
```

Sliding-window limiter. Waits when over the budget — never raises.

## Writing your own

```python
from fluxio.runtime.middleware import Middleware, Next

class MetricsMiddleware(Middleware):
    async def __call__(self, fn, ctx, next: Next):
        start = time.monotonic()
        try:
            return await next(fn, ctx)
        finally:
            metrics.histogram(
                "stage.duration",
                time.monotonic() - start,
                tags={"stage": fn.__name__},
            )
```

`next(fn, ctx)` calls the rest of the chain and returns the resulting `Context`. You can transform `ctx` before calling `next`, inspect the result, or short-circuit entirely.
