# Middleware

Middleware оборачивают каждый вызов стейджа. Применяются в порядке объявления — внешний первым:

```python
Pipeline(
    [...],
    middleware=[
        CircuitBreakerMiddleware(),   # самый внешний
        RetryMiddleware(),            # внутри breaker
        CacheMiddleware(),            # ближе всех к стейджу
    ],
)
# Порядок вызова: CircuitBreaker → Retry → Cache → stage
```

## Встроенные middleware

### `RetryMiddleware`

```python
RetryMiddleware(
    max_attempts=3,
    backoff="exponential",   # "fixed" | "exponential" | "jitter"
    base_delay=0.5,
    exceptions=(Exception,),
)
```

Для STREAM-стейджей пропускается (retry дублировал бы уже отданные чанки).

### `CacheMiddleware`

```python
CacheMiddleware(
    store=InMemoryCache(),   # или кастомный CacheStore
    ttl=300,
    key_fn=None,             # по умолчанию sha256(node_id + ctx_snapshot)
)
```

Использует отдельный интерфейс `CacheStore` — кэш и чекпоинт-стор изолированы. Для STREAM пропускается.

### `CircuitBreakerMiddleware`

```python
CircuitBreakerMiddleware(
    failure_threshold=5,
    recovery_timeout=60.0,
)
```

Состояния: `closed → open → half_open`. В `open` сразу бросает `CircuitOpenError`.

### `RateLimitMiddleware`

```python
RateLimitMiddleware(rps=10.0)
```

Sliding-window лимитер. Когда бюджет исчерпан — ждёт, не бросает исключений.

## Свой middleware

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

`next(fn, ctx)` вызывает остаток цепочки и возвращает итоговый `Context`. Можно трансформировать `ctx` до вызова `next`, инспектировать результат или сделать short-circuit.
