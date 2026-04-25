# Middleware

Middleware — это обёртки вокруг каждого вызова стейджа. Через них удобно добавлять ретраи, кеширование, метрики и любую сквозную логику, которую неприятно дублировать в каждом стейдже.

Middleware применяются в порядке объявления: первый в списке — самый внешний, последний — ближе всего к стейджу.

```python
Pipeline(
    [...],
    middleware=[
        CircuitBreakerMiddleware(),   # самый внешний
        RetryMiddleware(),            # внутри breaker
        CacheMiddleware(),            # ближе всех к стейджу
    ],
)
# Порядок вызова: CircuitBreaker → Retry → Cache → стейдж
```

Порядок имеет значение: например, retry обычно ставят снаружи кеша (чтобы повторять только реальные обращения, а не попадания в кеш) и внутри circuit breaker'а (чтобы breaker считал каждую попытку отдельно).

## Встроенные middleware

### `RetryMiddleware`

Повторяет вызов при исключении с экспоненциальной задержкой:

```python
RetryMiddleware(
    max_attempts=3,
    backoff="exponential",   # "fixed" | "exponential" | "jitter"
    base_delay=0.5,
    exceptions=(Exception,),
)
```

STREAM-стейджи retry автоматически пропускает — повтор продублировал бы уже отданные клиенту чанки.

### `CacheMiddleware`

Кеширует результаты стейджей по ключу из node_id и снепшота контекста:

```python
CacheMiddleware(
    store=InMemoryCache(),   # или ваш CacheStore
    ttl=300,
    key_fn=None,             # по умолчанию sha256(node_id + ctx_snapshot)
)
```

Кеш и хранилище чекпоинтов — это **разные** интерфейсы (`CacheStore` и `CheckpointStore`). Сделано намеренно: цели и время жизни данных у них разные. STREAM-стейджи кеш тоже пропускает — кеширование живого генератора бессмысленно.

### `CircuitBreakerMiddleware`

Стандартный circuit breaker. После N подряд идущих ошибок переходит в `open` и какое-то время сразу бросает `CircuitOpenError`, не доходя до стейджа:

```python
CircuitBreakerMiddleware(
    failure_threshold=5,
    recovery_timeout=60.0,
)
```

Состояния: `closed → open → half_open → closed`.

### `RateLimitMiddleware`

Sliding-window лимитер запросов в секунду:

```python
RateLimitMiddleware(rps=10.0)
```

Когда бюджет исчерпан — middleware **ждёт**, а не бросает исключение. То есть он сглаживает поток, а не отбрасывает запросы.

## Свой middleware

Достаточно реализовать `__call__`. Вызов `next(fn, ctx)` запускает остаток цепочки и возвращает итоговый `Context`:

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

Внутри своего middleware можно: модифицировать `ctx` до вызова `next`, проверить или подменить результат после, или вообще не звать `next` и вернуть свой контекст (short-circuit) — всё это допустимо.
