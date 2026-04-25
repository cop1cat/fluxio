# Условный роутинг

Иногда дальнейший путь пайплайна зависит от данных: премиум-пользователь идёт в одну ветку, обычный — в другую. Для этого fluxio использует пару «стейдж-роутер + dict-блок».

## Как это выглядит

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

`router` возвращает `Send("premium", patch={...})`. Идущий следом dict выбирает, какую под-пайплайн выполнить. Опциональный `patch` применяется к контексту перед выбранной веткой — удобно, чтобы передать какие-то данные, относящиеся именно к этому маршруту. Когда ветка отработала, выполнение продолжается со следующей верхнеуровневой ноды (`finalize`).

## Что можно класть в значения dict

В качестве веток принимаются:

- список стейджей,
- одиночный стейдж,
- готовый объект `Pipeline` (его ноды распакуются в эту ветку).

```python
{
    "premium":  Pipeline([fast_llm, priority_queue]),
    "standard": [cheap_llm, normal_queue],
}
```

## Трассировка решений

Чтобы видеть, какие маршруты выбирались, добавьте `on_route` в callback:

```python
class Spy(BaseCallback):
    async def on_route(self, run_id, step, route):
        metrics.incr(f"route.{step}.{route}")
```

## Вложенные роутинги

Dict'ы можно вкладывать друг в друга — внутри ветки положите ещё одну пару `router → dict`. Единственное правило: каждый dict обязан идти сразу за стейджем, который возвращает `Send`. Если структура нарушена, компилятор скажет об этом сразу — на этапе сборки, а не в рантайме.
