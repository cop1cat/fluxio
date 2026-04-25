# Стейдж

**Стейдж** — это базовый кирпичик, из которого собираются пайплайны. По сути это обычная Python-функция, помеченная `@stage`: она принимает `Context`, что-то с ним делает и возвращает новый `Context` (или `Send`, если хочет переключить ветку — об этом ниже).

## Три типа стейджей, один декоратор

`@stage` сам определяет тип по сигнатуре функции — отдельных декораторов под каждый тип нет.

=== "ASYNC"

    Обычный async-стейдж. Подходит для всего, что делает `await`: сетевые запросы, БД, обращения к LLM.

    ```python
    @stage
    async def fetch_user(ctx):
        return ctx.set("user", await db.get(ctx["user_id"]))
    ```

=== "SYNC"

    Обычная синхронная функция. fluxio запустит её в пуле потоков, чтобы CPU-нагрузка не блокировала event loop. Удобно для хешей, парсинга, сериализации.

    ```python
    @stage
    def compute_hash(ctx):
        return ctx.set("hash", hashlib.sha256(ctx["blob"]).hexdigest())
    ```

=== "STREAM"

    Async-генератор. Любой `async def` с `yield` становится стримом — чанки доставляются по мере появления через `pipe.stream()` или callback. Дополнительно весь собранный список чанков пишется в `ctx[f"{node_id}_stream_result"]`, чтобы следующие стейджи могли его прочитать.

    ```python
    @stage
    async def llm_stream(ctx):
        async for chunk in llm.stream(ctx["prompt"]):
            yield chunk
    ```

## Объявление `reads` и `writes`

Если указать, какие ключи стейдж читает и какие пишет, fluxio получает две вещи бесплатно:

```python
@stage(reads=frozenset({"user_id"}), writes=frozenset({"user"}))
async def fetch_user(ctx): ...
```

- **Автоматический параллелизм.** Если два соседних стейджа не зависят друг от друга по данным, компилятор сам обернёт их в `Parallel([...])`. Никаких изменений в коде не нужно.
- **Раннее обнаружение конфликтов.** Если две ветки `Parallel` пишут в один и тот же ключ, компиляция упадёт с `CompilationError` — вы узнаете об этом до первого запуска, а не на проде.

## Параметры стейджа

```python
from pydantic import BaseModel

class UserInput(BaseModel):
    user_id: int

@stage(
    input_schema=UserInput,      # валидация входа перед вызовом
    output_schema=UserOutput,    # валидация выхода после вызова
    timeout=5.0,                 # asyncio.timeout вокруг вызова
)
async def fetch_user(ctx): ...
```

Схемы проверяются против `ctx.snapshot()`. Лишние ключи в контексте схему не ломают — она описывает только то, что нужно конкретному стейджу, а не весь набор данных.

## Возврат `Send` для роутинга

Если стейдж — это «роутер», который выбирает дальнейшую ветку, он возвращает `Send`:

```python
from fluxio import Send

@stage
async def route(ctx):
    if ctx["tier"] == "premium":
        return Send("premium", {"priority": "high"})
    return Send("standard")
```

Подробнее — в разделе [Условный роутинг](../guides/routing.md).
