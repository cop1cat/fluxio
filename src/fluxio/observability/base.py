from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluxio.context.context import Context


class BaseCallback:
    """Hook interface for pipeline observability.

    Subclass and override the events you care about; all hooks default to no-op.
    Attach via ``Pipeline(callbacks=[MyCallback()])``.

    **Exception contract.** Callbacks are best-effort. The interpreter wraps
    every dispatch in a guard: if your callback raises, the exception is
    logged at ``WARNING`` to the ``fluxio.interpreter`` logger and the
    pipeline continues. This protects user logic from flaky observability
    sinks (Langfuse outages, Prometheus push failures) and guarantees that
    a callback exception in ``on_error`` cannot replace the original stage
    exception in the user's traceback.

    If your callback needs to fail loudly, log/alert from inside it — do
    not rely on raising to halt the pipeline.
    """

    async def on_pipeline_start(self, run_id: str, ctx: Context) -> None: ...

    async def on_pipeline_end(self, run_id: str, ctx: Context, duration_ms: int) -> None: ...

    async def on_step_start(self, run_id: str, step: str, ctx: Context) -> None: ...

    async def on_step_end(self, run_id: str, step: str, ctx: Context, duration_ms: int) -> None: ...

    async def on_step_stream(self, run_id: str, step: str, chunk: Any) -> None: ...

    async def on_branch(self, run_id: str, branches: list[str]) -> None: ...

    async def on_route(self, run_id: str, step: str, route: str) -> None: ...

    async def on_error(self, run_id: str, step: str, error: Exception) -> None: ...

    async def on_checkpoint(self, run_id: str, step: str, ip: int) -> None: ...
