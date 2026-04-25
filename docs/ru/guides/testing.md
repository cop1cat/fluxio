# Тестирование

В fluxio есть небольшой набор утилит, чтобы юнит-тестировать стейджи и пайплайны без лишней обвязки.

## `make_ctx` — собрать контекст для теста

```python
from fluxio.testing.fixtures import make_ctx

ctx = make_ctx({"user_id": 1})
assert ctx["user_id"] == 1
```

## `StepHarness` — запустить один стейдж изолированно

Часто хочется проверить ровно одну функцию, не собирая весь пайплайн. `StepHarness` запускает стейдж сам по себе, при необходимости — с middleware:

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

Для STREAM-стейджей есть `harness.run_stream(ctx)` — он соберёт все чанки в обычный список.

### Проверка записей

Когда хочется убедиться, что стейдж записал ровно ожидаемые ключи и не больше:

```python
ctx_before = make_ctx({"user": fake_user})
ctx_after = await harness.run(ctx_before)
harness.assert_writes(ctx_before, ctx_after, keys={"profile"})
```

Эта проверка ловит и недостающие записи, и случайно подсунутые лишние.

## Прогон полного пайплайна

В интеграционных тестах самый чистый вариант — `async with Pipeline(...)` прямо внутри `async def test_...`:

```python
async def test_full_flow():
    async with Pipeline([fetch_user, enrich, finalize]) as pipe:
        result = await pipe.invoke({"user_id": 1})
    assert result["summary"].startswith("Alice")
```

## Полезные привычки

- В тестах, где важен порядок выполнения, ставьте `auto_parallel=False` — иначе компилятор может случайно распараллелить и сделать порядок зависимым от планировщика asyncio.
- Если тест проверяет логику чекпоинтов, явно передавайте `InMemoryStore()` — он детерминированный и изолирован от других тестов.
- Внешние зависимости (HTTP, БД) удобно мокать на границе стейджа: оборачивайте сетевой вызов в стейдж и подменяйте его фикстурой. Тогда основная логика остаётся как есть, а в тесте просто стоит другой стейдж.
