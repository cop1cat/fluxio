# Тестирование

fluxio поставляет небольшие утилиты для юнит-тестов пайплайнов и стейджей.

## `make_ctx`

```python
from fluxio.testing.fixtures import make_ctx

ctx = make_ctx({"user_id": 1})
assert ctx["user_id"] == 1
```

## `StepHarness`

Запуск одного стейджа изолированно, опционально с middleware:

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

`StepHarness.run_stream(ctx)` собирает все чанки STREAM-стейджа в список.

### Проверка записей

```python
ctx_before = make_ctx({"user": fake_user})
ctx_after = await harness.run(ctx_before)
harness.assert_writes(ctx_before, ctx_after, keys={"profile"})
```

Убеждается, что стейдж записал ровно ожидаемые ключи — ни больше, ни меньше.

## Прогон полного пайплайна

В интеграционных тестах используйте `async with Pipeline(...)` внутри `async def test_...`:

```python
async def test_full_flow():
    async with Pipeline([fetch_user, enrich, finalize]) as pipe:
        result = await pipe.invoke({"user_id": 1})
    assert result["summary"].startswith("Alice")
```

## Советы

- Используйте `auto_parallel=False` в тестах, если важен детерминированный порядок.
- Для проверки чекпоинтов явно передавайте `InMemoryStore()` — он детерминированный и изолированный per-test.
- Мокайте внешние зависимости на границе стейджа: заворачивайте сетевой вызов в стейдж и подменяйте через фикстуру.
