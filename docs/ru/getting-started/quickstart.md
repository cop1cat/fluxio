# Быстрый старт

Ниже — полный рабочий пример со всеми ключевыми частями fluxio. Дальше по документации каждый кусочек разобран подробно.

```python
import asyncio
from fluxio import Pipeline, Parallel, stage

# 1. Стейдж — обычная функция, помеченная @stage.
#    Принимает контекст, возвращает контекст.
@stage
async def fetch_user(ctx):
    return ctx.set("user", {"id": ctx["user_id"], "name": "Alice"})

# 2. Если объявить, что стейдж читает и что пишет,
#    fluxio сам найдёт независимые стейджи и распараллелит их.
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

# 3. Pipeline компилируется один раз; invoke можно вызывать
#    сколько угодно. async with закрывает внутренний пул потоков.
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

## Что здесь произошло

1. **`@stage`** превратил обычную функцию в стейдж. Тип (`ASYNC` / `SYNC` / `STREAM`) определился автоматически по сигнатуре.
2. **`Pipeline(...)`** прошёлся по списку стейджей и скомпилировал из них линейную программу — это происходит один раз, на старте.
3. **`pipe.invoke({...})`** запустил эту программу: интерпретатор по очереди вызывает стейджи, передавая между ними неизменяемый `Context`.
4. **`Parallel([...])`** запустил `enrich` и `fetch_orders` одновременно, а после завершения слил их записи обратно в общий контекст.
5. **`async with`** в конце корректно закрыл пул потоков, в котором выполняются синхронные стейджи.

## Что читать дальше

- [Стейдж](../concepts/stage.md) — что именно делает `@stage` и как объявлять зависимости.
- [Контекст](../concepts/context.md) — как устроена иммутабельность и почему это удобно.
- [Пайплайн](../concepts/pipeline.md) — все способы запуска и опции.
