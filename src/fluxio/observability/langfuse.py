from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fluxio.observability.base import BaseCallback

if TYPE_CHECKING:
    from fluxio.context.context import Context


class LangfuseCallback(BaseCallback):
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
        self._spans: dict[tuple[str, str | None], Any] = {}

    async def on_pipeline_start(self, run_id: str, ctx: Context) -> None:
        span = self._client.start_span(name=run_id)
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
        span = parent.start_span(name=step)
        self._spans[(run_id, step)] = span

    async def on_step_end(self, run_id: str, step: str, ctx: Context, duration_ms: int) -> None:
        span = self._spans.pop((run_id, step), None)
        if span is not None:
            span.update(metadata={"duration_ms": duration_ms})
            span.end()

    async def on_error(self, run_id: str, step: str, error: Exception) -> None:
        span = self._spans.get((run_id, step))
        if span is not None:
            span.update(metadata={"error": str(error)}, level="ERROR")
