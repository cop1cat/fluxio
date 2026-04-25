# Durable execution

Durable execution — это способность пайплайна пережить падение процесса и продолжить выполнение с того места, где он остановился. fluxio достигает этого через чекпоинты: между стейджами он сохраняет состояние контекста и текущую позицию в программе. Если что-то упало — перезапускаем с `resume=True`, и пайплайн продолжает с последнего успешного шага.

## Включение

```python
from fluxio import Pipeline, InMemoryStore

pipeline = Pipeline(
    nodes=[...],
    checkpoint_store=InMemoryStore(),
    durable=True,
)
```

Перед каждым вызовом стейджа интерпретатор сохраняет `ctx.snapshot()` вместе с указателем на текущую инструкцию. Если стейдж бросает исключение, перед тем как пробросить его наверх fluxio пишет финальный чекпоинт с `error=True` — чтобы можно было ретраить с правильного места.

## Свежий запуск против `resume`

По умолчанию каждый `invoke` — это **свежий запуск**. Если для переданного `run_id` уже есть чекпоинт, он удаляется и пайплайн стартует с нуля. Это безопасное поведение по умолчанию — случайно не перезапустить старое состояние.

Чтобы продолжить с последнего чекпоинта, явно передайте `resume=True`:

```python
# первый прогон упал
await pipeline.invoke({"user_id": 42}, run_id="req-1")

# позже, или внутри retry-цикла — продолжаем с того же места
await pipeline.invoke({}, run_id="req-1", resume=True)
```

Если чекпоинта для этого `run_id` не нашлось — `KeyError`.

## Версия пайплайна и устаревшие чекпоинты

У каждого скомпилированного пайплайна есть короткий sha256-хеш `version`. Когда пишется чекпоинт, версия сохраняется вместе с ним. Если вы пытаетесь сделать `resume` на пайплайне другой версии (то есть после изменений в коде), fluxio бросит `CheckpointVersionError`.

Это сделано намеренно: восстановление старого состояния поверх обновлённой логики почти наверняка сломает что-то тонкое. Лучше явно решить, что делать со старыми чекпоинтами, чем тихо получить странный баг.

## Конкурентность

`invoke(run_id="x")` с `durable=True` берёт лок на этот `run_id`. Если параллельно прилетит ещё один вызов с тем же id — он получит `RunIDInUseError`. Разные `run_id` друг другу не мешают.

## Хранилища чекпоинтов

### `InMemoryStore` (по умолчанию)

Обычный `dict` внутри процесса с `asyncio.Lock`. Идеален для тестов и однопроцессных сервисов, где переживать рестарт процесса не требуется.

### `RedisStore`

Когда чекпоинты должны переживать рестарт процесса или быть доступны нескольким воркерам:

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

### Свой бэкенд

Достаточно реализовать четыре метода интерфейса `CheckpointStore`:

```python
from fluxio.store.base import CheckpointStore, Checkpoint

class PostgresStore(CheckpointStore):
    async def save(self, checkpoint: Checkpoint) -> None: ...
    async def load(self, run_id: str) -> Checkpoint | None: ...
    async def delete(self, run_id: str) -> None: ...
    async def exists(self, run_id: str) -> bool: ...
```

## Replay и diff

Если нужно перезапустить пайплайн с сохранённого состояния или сравнить два разных прогона по ключам контекста:

```python
# перезапуск с сохранённого чекпоинта
await pipeline.replay("req-1")

# что отличается между двумя прогонами
delta = await pipeline.diff("req-1", "req-2")
```
