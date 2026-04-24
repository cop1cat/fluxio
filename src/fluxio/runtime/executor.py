from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
from typing import TYPE_CHECKING, Any

from fluxio.api.primitives import NodeType

if TYPE_CHECKING:
    from concurrent.futures import ThreadPoolExecutor

    from fluxio.api.primitives import StageFunc
    from fluxio.context.context import Context


StreamEmit = Callable[[str, Any], Awaitable[None]]


class Executor:
    def __init__(self, thread_pool: ThreadPoolExecutor) -> None:
        self._thread_pool = thread_pool

    async def run(
        self,
        node_id: str,
        fn: StageFunc,
        ctx: Context,
        emit_stream: StreamEmit | None = None,
    ) -> Context | Any:
        node_type = getattr(fn, "__fluxio_node_type__", NodeType.ASYNC)
        if node_type == NodeType.ASYNC:
            return await fn(ctx)  # type: ignore[misc]
        if node_type == NodeType.SYNC:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._thread_pool, fn, ctx)
        if node_type == NodeType.STREAM:
            return await self._run_stream(node_id, fn, ctx, emit_stream)
        raise ValueError(f"Unknown node_type: {node_type}")

    async def _run_stream(
        self,
        node_id: str,
        fn: StageFunc,
        ctx: Context,
        emit_stream: StreamEmit | None,
    ) -> Context:
        accumulated: list[Any] = []
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=32)
        sentinel = object()

        async def producer() -> None:
            try:
                async for chunk in fn(ctx):  # type: ignore[attr-defined]
                    await queue.put(chunk)
            finally:
                await queue.put(sentinel)

        task = asyncio.create_task(producer())
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                accumulated.append(item)
                if emit_stream is not None:
                    await emit_stream(node_id, item)
            await task
        except BaseException:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            raise
        return ctx.set(f"{node_id}_stream_result", accumulated)
