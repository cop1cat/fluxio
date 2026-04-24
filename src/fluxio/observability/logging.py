from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fluxio.observability.base import BaseCallback

if TYPE_CHECKING:
    from fluxio.context.context import Context

_logger = logging.getLogger("fluxio")


class LoggingCallback(BaseCallback):
    def __init__(self, chunk_logging: bool = False) -> None:
        self.chunk_logging = chunk_logging

    async def on_pipeline_start(self, run_id: str, ctx: "Context") -> None:
        _logger.info("pipeline_start run_id=%s", run_id)

    async def on_pipeline_end(
        self, run_id: str, ctx: "Context", duration_ms: int
    ) -> None:
        _logger.info(
            "pipeline_end run_id=%s duration_ms=%d", run_id, duration_ms
        )

    async def on_step_start(
        self, run_id: str, step: str, ctx: "Context"
    ) -> None:
        _logger.debug("step_start run_id=%s step=%s", run_id, step)

    async def on_step_end(
        self, run_id: str, step: str, ctx: "Context", duration_ms: int
    ) -> None:
        _logger.debug(
            "step_end run_id=%s step=%s duration_ms=%d",
            run_id,
            step,
            duration_ms,
        )

    async def on_step_stream(
        self, run_id: str, step: str, chunk: Any
    ) -> None:
        if self.chunk_logging:
            _logger.debug(
                "step_stream run_id=%s step=%s chunk=%r", run_id, step, chunk
            )

    async def on_branch(self, run_id: str, branches: list[str]) -> None:
        _logger.debug("branch run_id=%s branches=%s", run_id, branches)

    async def on_error(
        self, run_id: str, step: str, error: Exception
    ) -> None:
        _logger.error(
            "error run_id=%s step=%s: %s",
            run_id,
            step,
            error,
            exc_info=True,
        )

    async def on_checkpoint(
        self, run_id: str, step: str, ip: int
    ) -> None:
        _logger.debug(
            "checkpoint run_id=%s step=%s ip=%d", run_id, step, ip
        )
