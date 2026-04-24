# Observability

Callbacks получают события от интерпретатора — используйте их для логирования, метрик, трассировки.

## События

Реализуйте любое подмножество `BaseCallback`; дефолты — no-op.

| Событие              | Когда                                                           |
|----------------------|------------------------------------------------------------------|
| `on_pipeline_start`  | перед первым стейджем                                            |
| `on_pipeline_end`    | после последнего стейджа                                         |
| `on_step_start`      | перед каждым стейджем                                            |
| `on_step_end`        | после каждого стейджа (с `duration_ms`)                          |
| `on_step_stream`     | каждый чанк из STREAM-стейджа                                    |
| `on_branch`          | когда стартует `Parallel`-блок (id веток)                        |
| `on_route`           | когда роутер отрезолвил `Send` (стейдж + выбранный маршрут)      |
| `on_error`           | любое исключение внутри стейджа                                  |
| `on_checkpoint`      | после записи durable-чекпоинта                                   |

## `LoggingCallback`

Готовый callback через стандартный logger:

```python
from fluxio import LoggingCallback

Pipeline([...], callbacks=[LoggingCallback()])
```

Пишет события под logger'ом `fluxio`. `pipeline_start/end` — `INFO`, всё остальное — `DEBUG`.

## `LangfuseCallback`

Требует `pip install fluxio[langfuse]`. Создаёт root-span на прогон и child-spans на каждый стейдж через Langfuse SDK v3.

```python
from fluxio.observability.langfuse import LangfuseCallback

cb = LangfuseCallback(
    public_key="pk_...",
    secret_key="sk_...",
    host="https://cloud.langfuse.com",
)
Pipeline([...], callbacks=[cb])
```

## Свой callback

```python
from fluxio import BaseCallback

class PromCallback(BaseCallback):
    async def on_step_end(self, run_id, step, ctx, duration_ms):
        STAGE_DURATION.labels(step=step).observe(duration_ms / 1000)

    async def on_error(self, run_id, step, error):
        STAGE_ERRORS.labels(step=step, kind=type(error).__name__).inc()
```

Callbacks работают в цикле интерпретатора — не блокируйте их. Тяжёлую работу выносите в очередь.
