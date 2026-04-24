# Streaming

STREAM stages yield chunks as they are produced — perfect for LLM responses, SSE endpoints, WebSockets.

## Writing a STREAM stage

Any `async def` generator becomes a STREAM stage:

```python
@stage
async def llm_response(ctx):
    async for chunk in llm.stream(ctx["prompt"]):
        yield chunk
```

## Consuming chunks

### `pipe.stream(...)`

```python
async with Pipeline([ingest, llm_response]) as pipe:
    async for chunk in pipe.stream({"prompt": "Hello"}):
        await websocket.send(chunk)
```

`stream()` yields raw chunks. All non-STREAM stages still run in order; their side effects happen before/after the streaming stage as declared.

### `on_step_stream` callback

When you need to tag chunks by stage:

```python
class Tap(BaseCallback):
    async def on_step_stream(self, run_id, step, chunk):
        print(f"[{step}] {chunk}")

Pipeline([...], callbacks=[Tap()])
```

## Accumulated result in context

After a STREAM stage finishes, the collected chunks are also stored at `ctx[f"{node_id}_stream_result"]`, so downstream stages can see them:

```python
@stage
async def save_transcript(ctx):
    chunks = ctx["llm_response_stream_result"]
    await db.save("\n".join(chunks))
```

## Backpressure

There's a bounded `asyncio.Queue(maxsize=32)` between the producer (the generator) and the consumer (callbacks + the `stream()` output). If the consumer is slow, the generator is automatically throttled.

## Middlewares and STREAM

`RetryMiddleware` and `CacheMiddleware` **bypass** STREAM stages automatically — retrying would produce duplicate chunks, and caching a live generator is meaningless.

Other middlewares (rate limit, circuit breaker, custom) apply normally.
