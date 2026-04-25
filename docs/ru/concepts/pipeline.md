# Пайплайн

`Pipeline` компилирует список стейджей, `Parallel`-блоков и dict-роутинга в байткод и управляет запусками.

## Создание

```python
async with Pipeline(
    nodes=[stage_a, stage_b, Parallel([c, d]), router, {"x": [e], "y": [f]}],
    middleware=[RetryMiddleware(), CacheMiddleware()],
    callbacks=[LoggingCallback()],
    checkpoint_store=InMemoryStore(),
    durable=True,
    max_workers=8,
    auto_parallel=True,
) as pipe:
    ...
```

- Компиляция происходит **один раз**, в `__init__`. Результат доступен в `pipe.version` (короткий sha256).
- `async with` — рекомендуемая форма: закрывает внутренний thread pool на выходе.

## Запуск

### `invoke`

```python
result: Context = await pipe.invoke({"user_id": 42})
```

С durable execution:

```python
# первая попытка упала посреди пайплайна
await pipe.invoke({"user_id": 42}, run_id="req-1")

# возобновление с последнего чекпоинта
await pipe.invoke({}, run_id="req-1", resume=True)
```

### `stream`

Yield'ит чанки из STREAM-стейджей по мере их появления:

```python
async with Pipeline([ingest, llm_stream]) as pipe:
    async for chunk in pipe.stream({"prompt": "привет"}):
        await websocket.send(chunk)
```

### `run_step`

Запускает один стейдж изолированно — удобно для тестов:

```python
out = await pipe.run_step("fetch_user", {"user_id": 1})
```

### `replay`

Перезапуск пайплайна от сохранённого чекпоинта. Нужен `durable=True`:

```python
await pipe.replay("req-1")
```

### `explain`

Человеко-читаемая структура скомпилированного пайплайна, включая маршруты и параллельные блоки:

```python
print(pipe.explain())
```

## Важные гарантии

- Параллельный `invoke(run_id="x")` с `durable=True` на одном пайплайне бросает `RunIDInUseError`.
- STREAM-стейджи автоматически обходят `RetryMiddleware` и `CacheMiddleware` — частичные чанки уже доставлены.
- `async with` можно не использовать для чисто-async пайплайнов, но тогда вызывайте `pipe.shutdown()` вручную.
