from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluxio.context.context import Context


class BaseCallback:
    async def on_pipeline_start(self, run_id: str, ctx: "Context") -> None: ...

    async def on_pipeline_end(
        self, run_id: str, ctx: "Context", duration_ms: int
    ) -> None: ...

    async def on_step_start(
        self, run_id: str, step: str, ctx: "Context"
    ) -> None: ...

    async def on_step_end(
        self, run_id: str, step: str, ctx: "Context", duration_ms: int
    ) -> None: ...

    async def on_step_stream(
        self, run_id: str, step: str, chunk: Any
    ) -> None: ...

    async def on_branch(self, run_id: str, branches: list[str]) -> None: ...

    async def on_error(
        self, run_id: str, step: str, error: Exception
    ) -> None: ...

    async def on_checkpoint(
        self, run_id: str, step: str, ip: int
    ) -> None: ...
