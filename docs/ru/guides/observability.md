# Observability

Callback'и получают события от интерпретатора по ходу выполнения пайплайна — через них удобно подключать логирование, метрики и трассировку.

## События

Реализуйте те методы `BaseCallback`, которые вам нужны — все остальные по умолчанию ничего не делают.

| Событие              | Когда срабатывает                                                |
|----------------------|------------------------------------------------------------------|
| `on_pipeline_start`  | перед самым первым стейджем                                      |
| `on_pipeline_end`    | после самого последнего стейджа                                  |
| `on_step_start`      | перед каждым стейджем                                            |
| `on_step_end`        | после каждого стейджа (с `duration_ms`)                          |
| `on_step_stream`     | на каждый чанк из STREAM-стейджа                                 |
| `on_branch`          | при старте `Parallel`-блока (с id веток)                         |
| `on_route`           | когда роутер выбрал ветку (стейдж + имя маршрута)                |
| `on_error`           | при любом исключении внутри стейджа                              |
| `on_checkpoint`      | после записи durable-чекпоинта                                   |

## `LoggingCallback`

Готовый callback, пишущий через стандартный `logging`:

```python
from fluxio import LoggingCallback

Pipeline([...], callbacks=[LoggingCallback()])
```

Все события идут в logger с именем `fluxio`. `pipeline_start` и `pipeline_end` пишутся на уровне `INFO`, остальные — на `DEBUG`.

## `LangfuseCallback`

Создаёт root-span на весь прогон и child-span на каждый стейдж через Langfuse SDK v3:

```python
from fluxio.observability.langfuse import LangfuseCallback

cb = LangfuseCallback(
    public_key="pk_...",
    secret_key="sk_...",
    host="https://cloud.langfuse.com",
)
Pipeline([...], callbacks=[cb])
```

Требует `pip install fluxio[langfuse]`.

## Свой callback

```python
from fluxio import BaseCallback

class PromCallback(BaseCallback):
    async def on_step_end(self, run_id, step, ctx, duration_ms):
        STAGE_DURATION.labels(step=step).observe(duration_ms / 1000)

    async def on_error(self, run_id, step, error):
        STAGE_ERRORS.labels(step=step, kind=type(error).__name__).inc()
```

Важный момент: callback'и выполняются прямо в цикле интерпретатора. Тяжёлые операции (запись в БД, отправка по сети) лучше класть в очередь и обрабатывать отдельным воркером — иначе медленный callback будет тормозить весь пайплайн.
