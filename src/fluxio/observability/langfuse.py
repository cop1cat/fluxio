from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fluxio.observability.base import BaseCallback

if TYPE_CHECKING:
    from fluxio.context.context import Context


class LangfuseCallback(BaseCallback):
    """Trace fluxio pipelines into Langfuse v3+ via the ``start_observation`` API.

    A root observation is opened for each ``run_id``; every stage gets a
    child observation. Spans are always closed — including on errors and
    pipeline failure — so dashboards never show open-ended traces.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
    ) -> None:
        try:
            from langfuse import Langfuse
        except ImportError as e:
            raise ImportError(
                "langfuse is required for LangfuseCallback. "
                "Install with: pip install fluxio[langfuse]"
            ) from e
        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        # Stored under (run_id, step_name) — step_name is None for the root.
        self._spans: dict[tuple[str, str | None], Any] = {}

    def _start_observation(self, parent: Any, name: str) -> Any:
        # Langfuse v3 introduced ``start_observation``; v2 used ``start_span``.
        # Support both so callers can pin either.
        if hasattr(parent, "start_observation"):
            return parent.start_observation(name=name, as_type="span")
        return parent.start_span(name=name)

    async def on_pipeline_start(self, run_id: str, ctx: Context) -> None:
        span = self._start_observation(self._client, run_id)
        self._spans[(run_id, None)] = span

    async def on_pipeline_end(self, run_id: str, ctx: Context, duration_ms: int) -> None:
        span = self._spans.pop((run_id, None), None)
        if span is not None:
            span.update(metadata={"duration_ms": duration_ms})
            span.end()

    async def on_step_start(self, run_id: str, step: str, ctx: Context) -> None:
        parent = self._spans.get((run_id, None))
        if parent is None:
            return
        span = self._start_observation(parent, step)
        self._spans[(run_id, step)] = span

    async def on_step_end(self, run_id: str, step: str, ctx: Context, duration_ms: int) -> None:
        span = self._spans.pop((run_id, step), None)
        if span is not None:
            span.update(metadata={"duration_ms": duration_ms})
            span.end()

    async def on_error(self, run_id: str, step: str, error: Exception) -> None:
        # End the failing step's span with error context if it's still open.
        # ``on_step_end`` will not fire for a CALL that raised, but the
        # interpreter's error path also closes timers — this is defensive.
        step_span = self._spans.pop((run_id, step), None)
        if step_span is not None:
            step_span.update(metadata={"error": str(error)}, level="ERROR")
            step_span.end()
        # The pipeline failed, so ``on_pipeline_end`` will not fire either.
        # Close the root span so the trace is visible in Langfuse.
        root = self._spans.pop((run_id, None), None)
        if root is not None:
            root.update(metadata={"error": str(error)}, level="ERROR")
            root.end()
