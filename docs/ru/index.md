# fluxio

Streamable, durable pipeline runtime для Python-бэкендов.

## Зачем нужен fluxio

- **Композиция из стейджей** — декорируете обычные функции `@stage`. Sync / async / streaming определяются автоматически.
- **Immutable HAMT-контекст** — каждый `ctx.set()` возвращает новый контекст со structural sharing. Fork — O(1), merge ловит конфликты записи.
- **Авто-параллелизм** — объявляете `reads` / `writes`, компилятор сам распараллеливает независимые стейджи.
- **Durable execution** — чекпоинты между стейджами, возобновление после падения через явный `resume=True`.
- **Условный роутинг** — `Send("route-name")` направляет выполнение в нужный dict-блок под-пайплайна.
- **Стриминг** — генератор `yield`'ит чанки, потребляются через `pipe.stream()` или callback `on_step_stream`.
- **Батарейки включены** — retry, cache, circuit breaker, rate limit; LoggingCallback и LangfuseCallback; InMemory и Redis стор.

## Пример на 30 секунд

```python
from fluxio import Pipeline, stage

@stage
async def fetch_user(ctx):
    return ctx.set("user", {"id": ctx["user_id"], "name": "Alice"})

@stage
async def greet(ctx):
    return ctx.set("greeting", f"Hello {ctx['user']['name']}")

async with Pipeline([fetch_user, greet]) as pipe:
    result = await pipe.invoke({"user_id": 1})
    print(result["greeting"])
```

## Куда двигаться дальше

- [Установка](getting-started/installation.md)
- [Быстрый старт](getting-started/quickstart.md)
- [Концепции: Стейдж](concepts/stage.md) — единица композиции
- [Руководства: Durable execution](guides/durable.md) — отказоустойчивые пайплайны
- [Справочник API](reference/api.md)
