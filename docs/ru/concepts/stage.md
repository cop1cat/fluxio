# Стейдж

**Стейдж** — единица композиции в fluxio. Это любая функция с декоратором `@stage`, принимающая `Context` и возвращающая `Context` (или `Send` для роутинга).

## Три вкуса, один декоратор

Тип стейджа определяется автоматически по сигнатуре функции:

=== "ASYNC"

    ```python
    @stage
    async def fetch_user(ctx):
        return ctx.set("user", await db.get(ctx["user_id"]))
    ```

=== "SYNC"

    ```python
    @stage
    def compute_hash(ctx):
        return ctx.set("hash", hashlib.sha256(ctx["blob"]).hexdigest())
    ```

    SYNC-стейджи запускаются в thread pool, чтобы CPU-нагрузка не блокировала event loop.

=== "STREAM"

    ```python
    @stage
    async def llm_stream(ctx):
        async for chunk in llm.stream(ctx["prompt"]):
            yield chunk
    ```

    Любой `async def` с `yield` становится STREAM-стейджем. Чанки доставляются через `pipe.stream()`, а полный список также попадает в `ctx[f"{node_id}_stream_result"]`.

## Объявленные reads / writes

```python
@stage(reads=frozenset({"user_id"}), writes=frozenset({"user"}))
async def fetch_user(ctx): ...
```

Объявление `reads` / `writes` даёт две вещи:

- **Авто-параллелизм.** Последовательные стейджи с непересекающимися зависимостями оборачиваются в неявный `Parallel([...])` на этапе компиляции.
- **Детект конфликтов записи.** Если две ветки `Parallel` пишут в один ключ, компиляция падает с `CompilationError`.

## Параметры стейджа

```python
from pydantic import BaseModel

class UserInput(BaseModel):
    user_id: int

@stage(
    input_schema=UserInput,      # валидация перед CALL
    output_schema=UserOutput,    # валидация после CALL
    timeout=5.0,                 # asyncio.timeout вокруг вызова
)
async def fetch_user(ctx): ...
```

Схемы валидируются против `ctx.snapshot()`. Лишние ключи игнорируются — схема описывает что стейджу нужно / что он выдаёт, не весь мир.

## Возврат `Send` для роутинга

```python
from fluxio import Send

@stage
async def route(ctx):
    if ctx["tier"] == "premium":
        return Send("premium", {"priority": "high"})
    return Send("standard")
```

См. [Условный роутинг](../guides/routing.md).
