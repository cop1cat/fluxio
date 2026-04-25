# Стриминг

STREAM-стейджи отдают данные по мере их генерации, не дожидаясь финального результата. Это нужно для всего, где задержка до первого байта критична: ответы LLM, SSE-эндпоинты, WebSocket'ы.

## Как написать STREAM-стейдж

Любой `async def`-генератор автоматически становится STREAM-стейджем — отдельного декоратора не нужно:

```python
@stage
async def llm_response(ctx):
    async for chunk in llm.stream(ctx["prompt"]):
        yield chunk
```

## Как читать чанки

### `pipe.stream(...)`

Простой случай — отдавать чанки клиенту:

```python
async with Pipeline([ingest, llm_response]) as pipe:
    async for chunk in pipe.stream({"prompt": "Привет"}):
        await websocket.send(chunk)
```

`stream()` отдаёт сами чанки, без обвески. Не-STREAM стейджи при этом всё равно выполняются в обычном порядке — их побочные эффекты случатся до или после стримингового стейджа.

### Callback `on_step_stream`

Если нужно различать чанки от разных стейджей или подключить трассировку:

```python
class Tap(BaseCallback):
    async def on_step_stream(self, run_id, step, chunk):
        print(f"[{step}] {chunk}")

Pipeline([...], callbacks=[Tap()])
```

## Собранный результат в контексте

Когда STREAM-стейдж заканчивается, все его чанки также лежат в `ctx[f"{node_id}_stream_result"]` — следующие стейджи могут прочитать полный результат:

```python
@stage
async def save_transcript(ctx):
    chunks = ctx["llm_response_stream_result"]
    await db.save("\n".join(chunks))
```

То есть один и тот же стейдж работает и как стрим (для клиента), и как обычная функция, кладущая результат в контекст (для остальных стейджей).

## Backpressure

Между генератором и потребителем стоит ограниченная очередь — `asyncio.Queue(maxsize=32)`. Если потребитель не успевает читать, генератор автоматически приостанавливается, пока место не освободится. Утечки памяти от медленных клиентов не будет.

## Middleware и STREAM

`RetryMiddleware` и `CacheMiddleware` STREAM-стейджи **пропускают** автоматически: повтор продублировал бы уже отданные чанки, а кеширование живого генератора бессмысленно.

Остальные middleware (rate limit, circuit breaker, ваши собственные) работают со STREAM как обычно.
