# Observability

Callbacks receive events from the interpreter — use them for logging, metrics, tracing.

## Events

Implement any subset on `BaseCallback`; defaults are no-op.

| Event                | When                                                         |
|----------------------|--------------------------------------------------------------|
| `on_pipeline_start`  | before the first stage                                       |
| `on_pipeline_end`    | after the last stage                                         |
| `on_step_start`      | before each stage                                            |
| `on_step_end`        | after each stage (with `duration_ms`)                        |
| `on_step_stream`     | every chunk yielded by a STREAM stage                        |
| `on_branch`          | when a `Parallel` block begins (branch node ids)             |
| `on_route`           | when a router's `Send` is resolved (step + chosen route)     |
| `on_error`           | any exception inside a stage                                 |
| `on_checkpoint`      | after a durable checkpoint is written                        |

## `LoggingCallback`

Ready-to-use standard-library logger:

```python
from fluxio import LoggingCallback

Pipeline([...], callbacks=[LoggingCallback()])
```

Logs events under the `fluxio` logger. `pipeline_start/end` at `INFO`, everything else at `DEBUG`.

## `LangfuseCallback`

Requires `pip install fluxio[langfuse]`. Creates a root span per run and child spans per stage using Langfuse SDK v3.

```python
from fluxio.observability.langfuse import LangfuseCallback

cb = LangfuseCallback(
    public_key="pk_...",
    secret_key="sk_...",
    host="https://cloud.langfuse.com",
)
Pipeline([...], callbacks=[cb])
```

## Custom callbacks

```python
from fluxio import BaseCallback

class PromCallback(BaseCallback):
    async def on_step_end(self, run_id, step, ctx, duration_ms):
        STAGE_DURATION.labels(step=step).observe(duration_ms / 1000)

    async def on_error(self, run_id, step, error):
        STAGE_ERRORS.labels(step=step, kind=type(error).__name__).inc()
```

Callbacks run in the interpreter loop — don't block. Offload heavy work to a queue.
