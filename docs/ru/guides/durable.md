# Durable execution

fluxio умеет сохранять состояние между стейджами и возобновлять упавший прогон с последнего чекпоинта.

## Включение durability

```python
from fluxio import Pipeline, InMemoryStore

pipeline = Pipeline(
    nodes=[...],
    checkpoint_store=InMemoryStore(),
    durable=True,
)
```

Перед каждой инструкцией `CALL` интерпретатор сохраняет `ctx.snapshot()` вместе с instruction pointer. Если стейдж падает с исключением, пишется финальный чекпоинт с `error=True`, затем исключение пробрасывается.

## Свежий прогон vs resume

Поведение по умолчанию — **всегда свежий прогон**. Если чекпоинт для данного `run_id` существует, он удаляется и прогон стартует с нуля.

Чтобы продолжить с последнего чекпоинта, передайте `resume=True`:

```python
# прогон упал здесь
await pipeline.invoke({"user_id": 42}, run_id="req-1")

# позже, или в retry-цикле
await pipeline.invoke({}, run_id="req-1", resume=True)
```

Если чекпоинта для `run_id` нет — `KeyError`.

## Версионирование пайплайна

У каждого `CompiledPipeline` есть короткий sha256 `version`. Чекпоинт хранит версию, против которой он был сделан. Попытка resume на пайплайне другой версии — `CheckpointVersionError`: изменения кода не должны тихо бежать против устаревшего состояния.

## Конкурентность

`invoke(run_id="x")` с `durable=True` берёт лок на `run_id`. Второй параллельный вызов с тем же id бросает `RunIDInUseError`. Разные `run_id` — без ограничений.

## Сторы

### `InMemoryStore` (по умолчанию)

Process-local dict с `asyncio.Lock`. Идеален для тестов и одно-процессных сервисов.

### `RedisStore`

```python
from fluxio import RedisStore

pipeline = Pipeline(
    ...,
    checkpoint_store=RedisStore(
        url="redis://localhost:6379",
        ttl=86400,
        key_prefix="fluxio:checkpoint",
    ),
    durable=True,
)
```

Ставится через `pip install fluxio[redis]`.

### Кастомные бэкенды

Реализуйте `CheckpointStore`:

```python
from fluxio.store.base import CheckpointStore, Checkpoint

class PostgresStore(CheckpointStore):
    async def save(self, checkpoint: Checkpoint) -> None: ...
    async def load(self, run_id: str) -> Checkpoint | None: ...
    async def delete(self, run_id: str) -> None: ...
    async def exists(self, run_id: str) -> bool: ...
```

## Replay и diff

```python
# перезапуск с сохранённого чекпоинта
await pipeline.replay("req-1")

# сравнение двух прогонов по ключам
delta = await pipeline.diff("req-1", "req-2")
```
