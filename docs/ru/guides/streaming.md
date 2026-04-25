# Стриминг

STREAM-стейджи отдают чанки по мере генерации — идеально для LLM-ответов, SSE-эндпоинтов, WebSocket'ов.

## Написание STREAM-стейджа

Любой `async def`-генератор становится STREAM-стейджем:

```python
@stage
async def llm_response(ctx):
    async for chunk in llm.stream(ctx["prompt"]):
        yield chunk
```

## Потребление чанков

### `pipe.stream(...)`

```python
async with Pipeline([ingest, llm_response]) as pipe:
    async for chunk in pipe.stream({"prompt": "Привет"}):
        await websocket.send(chunk)
```

`stream()` yield'ит сырые чанки. Все не-STREAM стейджи всё равно выполняются в порядке объявления; их побочные эффекты случаются до/после стримингового стейджа.

### callback `on_step_stream`

Когда нужно различать чанки по стейджу:

```python
class Tap(BaseCallback):
    async def on_step_stream(self, run_id, step, chunk):
        print(f"[{step}] {chunk}")

Pipeline([...], callbacks=[Tap()])
```

## Накопленный результат в контексте

После завершения STREAM-стейджа собранные чанки также лежат в `ctx[f"{node_id}_stream_result"]`, так что следующие стейджи могут их прочитать:

```python
@stage
async def save_transcript(ctx):
    chunks = ctx["llm_response_stream_result"]
    await db.save("\n".join(chunks))
```

## Backpressure

Между продюсером (генератором) и консьюмером (callbacks + вывод `stream()`) — ограниченная `asyncio.Queue(maxsize=32)`. Если консьюмер медленный, продюсер автоматически притормаживается.

## Middlewares и STREAM

`RetryMiddleware` и `CacheMiddleware` **пропускают** STREAM-стейджи автоматически — retry дублировал бы чанки, кешировать живой генератор бессмысленно.

Остальные middleware (rate limit, circuit breaker, кастомные) работают как обычно.
