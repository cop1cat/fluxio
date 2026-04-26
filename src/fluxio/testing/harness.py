from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from typing import TYPE_CHECKING, Any

from fluxio.api.primitives import Send
from fluxio.context.context import Context
from fluxio.runtime.executor import Executor
from fluxio.runtime.middleware import MiddlewareChain

if TYPE_CHECKING:
    from fluxio.api.primitives import StageFunc
    from fluxio.runtime.middleware import Middleware


class StepHarness:
    def __init__(
        self,
        fn: StageFunc,
        middleware: list[Middleware] | None = None,
    ) -> None:
        self._fn = fn
        self._chain = MiddlewareChain(list(middleware or []))
        self._thread_pool = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
        self._executor = Executor(self._thread_pool)

    async def run(self, ctx: dict[str, Any] | Context) -> Context:
        c = ctx if isinstance(ctx, Context) else Context.create(ctx)
        node_id = getattr(self._fn, "__name__", "stage")

        async def terminal(fn: StageFunc, cc: Context) -> Any:
            return await self._executor.run(node_id, fn, cc, None)

        result = await self._chain.run(self._fn, c, terminal)
        if isinstance(result, Send):
            return c.update(result.patch)
        return result

    async def run_stream(self, ctx: dict[str, Any] | Context) -> list[Any]:
        c = ctx if isinstance(ctx, Context) else Context.create(ctx)
        node_id = getattr(self._fn, "__name__", "stage")
        chunks: list[Any] = []

        async def emit(_nid: str, chunk: Any) -> None:
            chunks.append(chunk)

        async def terminal(fn: StageFunc, cc: Context) -> Any:
            return await self._executor.run(node_id, fn, cc, emit)

        # Go through the middleware chain so harness behaviour matches
        # production. RetryMiddleware and CacheMiddleware self-bypass for
        # STREAM stages, so this does not duplicate or freeze chunks.
        await self._chain.run(self._fn, c, terminal)
        return chunks

    @staticmethod
    def assert_writes(ctx_before: Context, ctx_after: Context, keys: set[str]) -> None:
        actual = ctx_after._written
        expected = frozenset(keys)
        if actual != expected:
            raise AssertionError(f"Expected writes={sorted(expected)}, got={sorted(actual)}")

    def close(self) -> None:
        self._thread_pool.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> StepHarness:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aenter__(self) -> StepHarness:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.close()
