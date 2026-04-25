from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from typing import TYPE_CHECKING

from fluxio.api.primitives import ForkMode
from fluxio.runtime.executor import Executor

if TYPE_CHECKING:
    from fluxio.api.primitives import StageFunc
    from fluxio.context.context import Context

_logger = logging.getLogger("fluxio.scheduler")

BranchRun = Callable[["StageFunc", "Context", str], Awaitable["Context"]]


class Scheduler:
    def __init__(self, max_workers: int | None = None) -> None:
        workers = max_workers or os.cpu_count() or 4
        self._thread_pool = ThreadPoolExecutor(max_workers=workers)
        self.executor = Executor(self._thread_pool)

    async def run_parallel(
        self,
        branches: list[tuple[str, StageFunc, Context]],
        mode: ForkMode,
        runner: BranchRun,
    ) -> list[Context]:
        coros = [runner(fn, ctx, nid) for nid, fn, ctx in branches]
        if mode == ForkMode.PARALLEL:
            return list(await asyncio.gather(*coros, return_exceptions=False))
        results = await asyncio.gather(*coros, return_exceptions=True)
        out: list[Context] = []
        for (nid, _, ctx), res in zip(branches, results, strict=True):
            if isinstance(res, BaseException):
                _logger.error("fire-and-forget branch %s failed: %s", nid, res)
                out.append(ctx)
            else:
                out.append(res)
        return out

    def shutdown(self) -> None:
        self._thread_pool.shutdown(wait=False, cancel_futures=True)
