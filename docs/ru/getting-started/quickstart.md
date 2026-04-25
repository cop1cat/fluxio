# Быстрый старт

Все ключевые элементы в одном файле.

```python
import asyncio
from fluxio import Pipeline, Parallel, stage

# 1. Стейджи — любые функции с @stage.
@stage
async def fetch_user(ctx):
    return ctx.set("user", {"id": ctx["user_id"], "name": "Alice"})

# 2. Объявленные reads/writes включают авто-параллелизм и детект конфликтов.
@stage(reads=frozenset({"user"}), writes=frozenset({"profile"}))
async def enrich(ctx):
    return ctx.set("profile", {"bio": "..."})

@stage(reads=frozenset({"user"}), writes=frozenset({"orders"}))
async def fetch_orders(ctx):
    return ctx.set("orders", [1, 2, 3])

@stage
async def finalize(ctx):
    return ctx.set(
        "summary",
        f"У {ctx['user']['name']} {len(ctx['orders'])} заказов",
    )

# 3. Компилируется один раз, invoke — сколько угодно. async with закрывает пул.
async def main() -> None:
    async with Pipeline(
        [
            fetch_user,
            Parallel([enrich, fetch_orders]),
            finalize,
        ],
    ) as pipe:
        result = await pipe.invoke({"user_id": 42})
        print(result["summary"])  # У Alice 3 заказов

asyncio.run(main())
```

## Что произошло

1. **`@stage`** навесил метаданные на функцию. Тип стейджа (`ASYNC` / `SYNC` / `STREAM`) определён по сигнатуре.
2. **`Pipeline(...)`** скомпилировал ноды в линейный байткод один раз.
3. **`pipe.invoke({...})`** запустил программу, передавая неизменяемый `Context` между стейджами.
4. **`Parallel([...])`** выполнил `enrich` и `fetch_orders` параллельно и смержил их записи.
5. **`async with`** закрыл thread pool, используемый для `SYNC`-стейджей.

Дальше: подробно про [Стейдж](../concepts/stage.md), [Контекст](../concepts/context.md) и [Пайплайн](../concepts/pipeline.md).
