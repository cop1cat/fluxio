# Условный роутинг

Ветвление пайплайна в рантайме на основе данных.

## Основы

```python
from fluxio import Pipeline, Send, stage

@stage
async def classify(ctx):
    tier = "premium" if ctx["user"]["plan"] == "pro" else "standard"
    return ctx.set("tier", tier)

@stage
async def router(ctx):
    if ctx["tier"] == "premium":
        return Send("premium", {"priority": "high"})
    return Send("standard")

@stage
async def fast_llm(ctx): return ctx.set("answer", "fast")

@stage
async def cheap_llm(ctx): return ctx.set("answer", "cheap")

@stage
async def finalize(ctx): return ctx.set("done", True)

pipeline = Pipeline([
    classify,
    router,
    {
        "premium":  [fast_llm],
        "standard": [cheap_llm],
    },
    finalize,
])
```

`router` возвращает `Send("premium", patch={...})`. Dict, идущий следом, выбирает какую под-pipeline запустить. `patch` применяется к контексту перед выполнением выбранной ветки. После завершения ветки выполнение продолжается со следующей верхнеуровневой ноды (`finalize`).

## Значение маршрута

В dict-значении может быть:

- список стейджей
- один стейдж
- объект `Pipeline` (его ноды распакуются)

```python
{
    "premium":  Pipeline([fast_llm, priority_queue]),
    "standard": [cheap_llm, normal_queue],
}
```

## Трассировка

Добавьте `on_route` в callback чтобы видеть решения:

```python
class Spy(BaseCallback):
    async def on_route(self, run_id, step, route):
        metrics.incr(f"route.{step}.{route}")
```

## Вложенный роутинг

Dict'ы можно вкладывать: положите ещё одну пару `router → dict` внутри ветки. Каждый dict обязан следовать за стейджем, возвращающим `Send` — компилятор это проверяет.
