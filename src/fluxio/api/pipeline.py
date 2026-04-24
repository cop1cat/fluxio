from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any
import uuid

from fluxio.api.parallel import Parallel
from fluxio.api.primitives import NodeType
from fluxio.compiler.compiler import Compiler
from fluxio.context.context import Context
from fluxio.runtime.interpreter import Interpreter
from fluxio.runtime.middleware import MiddlewareChain
from fluxio.runtime.scheduler import Scheduler
from fluxio.store.memory import InMemoryStore

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from fluxio.api.primitives import StageFunc
    from fluxio.observability.base import BaseCallback
    from fluxio.runtime.middleware import Middleware
    from fluxio.store.base import CheckpointStore

_logger = logging.getLogger("fluxio.pipeline")

PipelineNode = "StageFunc | Parallel | dict[str, Any]"


class RunIDInUseError(RuntimeError):
    """Raised when a durable invoke is attempted with a run_id already in progress."""


class Pipeline:
    """Compiled, executable sequence of stages.

    Nodes are stages decorated with ``@stage``, ``Parallel(...)`` blocks, or
    ``dict[str, ...]`` routing blocks (following a stage that returns ``Send``).

    The pipeline is compiled once on construction. Use ``async with Pipeline(...)``
    to ensure the thread pool shuts down cleanly.

    Example::

        async with Pipeline([fetch_user, send_email]) as pipe:
            result = await pipe.invoke({"user_id": 42})
    """

    def __init__(
        self,
        nodes: list[StageFunc | Parallel | dict[str, Any]],
        *,
        middleware: list[Middleware] | None = None,
        callbacks: list[BaseCallback] | None = None,
        checkpoint_store: CheckpointStore | None = None,
        durable: bool = False,
        max_workers: int | None = None,
        auto_parallel: bool = True,
    ) -> None:
        self._nodes = list(nodes)
        self._middleware = list(middleware or [])
        self._callbacks = list(callbacks or [])
        self._store = checkpoint_store or (InMemoryStore() if durable else None)
        self._durable = durable
        self._compiled = Compiler(auto_parallel=auto_parallel).compile(self._nodes)
        self._scheduler = Scheduler(max_workers=max_workers)
        self._chain = MiddlewareChain(self._middleware)
        self._interpreter = Interpreter(self._scheduler, self._chain)
        self._active_runs: set[str] = set()

    @property
    def version(self) -> str:
        return self._compiled.version

    async def invoke(
        self,
        initial_ctx: dict[str, Any] | Context,
        *,
        run_id: str | None = None,
        resume: bool = False,
    ) -> Context:
        """Run the pipeline to completion and return the final context.

        Args:
            initial_ctx: Initial values as a dict or a ``Context`` instance.
            run_id: Identifier for this run. Auto-generated if not provided.
                With ``durable=True`` + ``resume=True``, must match an existing
                checkpoint.
            resume: If True, load checkpoint for ``run_id`` and continue.
                Raises ``KeyError`` if no checkpoint exists. Requires
                ``durable=True`` and a ``checkpoint_store``.
        """
        ctx = self._coerce_ctx(initial_ctx)
        rid = run_id or uuid.uuid4().hex
        async with self._acquire_run(rid):
            return await self._interpreter.run(
                self._compiled,
                ctx,
                rid,
                self._callbacks,
                store=self._store,
                durable=self._durable,
                resume=resume,
            )

    async def stream(
        self,
        initial_ctx: dict[str, Any] | Context,
        *,
        run_id: str | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Run the pipeline and yield chunks from STREAM stages as they arrive.

        Chunks from multiple STREAM stages are yielded in the order produced.
        Use an ``on_step_stream`` callback if you need to tag chunks by stage.
        """
        from fluxio.observability.base import BaseCallback

        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=32)
        sentinel = object()

        class _StreamCollector(BaseCallback):
            async def on_step_stream(self, rid_: str, step: str, chunk: Any) -> None:
                await queue.put(chunk)

        callbacks = [*self._callbacks, _StreamCollector()]
        ctx = self._coerce_ctx(initial_ctx)
        rid = run_id or uuid.uuid4().hex

        async def driver() -> None:
            try:
                await self._interpreter.run(
                    self._compiled,
                    ctx,
                    rid,
                    callbacks,
                    store=self._store,
                    durable=self._durable,
                )
            finally:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(sentinel)

        task = asyncio.create_task(driver())
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                yield item
            await task
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def run_step(
        self,
        step_name: str,
        ctx: dict[str, Any] | Context,
    ) -> Context:
        fn = self._compiled.symbol_table.get(step_name)
        if fn is None:
            raise KeyError(f"No stage named {step_name!r} in pipeline")
        c = self._coerce_ctx(ctx)
        from fluxio.api.primitives import Send

        async def terminal(f: StageFunc, cc: Context) -> Any:
            return await self._scheduler.executor.run(step_name, f, cc, None)

        result = await self._chain.run(fn, c, terminal)
        if isinstance(result, Send):
            return c.update(result.patch)
        return result

    async def replay(
        self,
        run_id: str,
        *,
        from_step: str | None = None,
    ) -> Context:
        if self._store is None:
            raise RuntimeError("replay requires a checkpoint_store")
        checkpoint = await self._store.load(run_id)
        if checkpoint is None:
            raise KeyError(f"No checkpoint for run_id={run_id!r}")
        ctx = Context.from_snapshot(checkpoint.ctx_snapshot, name="replay")
        if from_step is not None:
            ip = self._find_step_ip(from_step)
            await self._store.save(
                type(checkpoint)(
                    run_id=run_id,
                    pipeline_version=self._compiled.version,
                    ip=ip,
                    ctx_snapshot=ctx.snapshot(),
                    created_at=checkpoint.created_at,
                )
            )
        return await self._interpreter.run(
            self._compiled,
            ctx,
            run_id,
            self._callbacks,
            store=self._store,
            durable=True,
            resume=True,
        )

    async def diff(self, run_id_a: str, run_id_b: str) -> dict[str, Any]:
        if self._store is None:
            raise RuntimeError("diff requires a checkpoint_store")
        a = await self._store.load(run_id_a)
        b = await self._store.load(run_id_b)
        if a is None or b is None:
            raise KeyError("Both run_ids must have checkpoints")
        snap_a = a.ctx_snapshot
        snap_b = b.ctx_snapshot
        keys = set(snap_a) | set(snap_b)
        diff: dict[str, Any] = {}
        for k in sorted(keys):
            va, vb = snap_a.get(k), snap_b.get(k)
            if va != vb:
                diff[k] = {"a": va, "b": vb}
        return diff

    def explain(self) -> str:
        lines: list[str] = [
            f"Pipeline [version={self._compiled.version}, {len(self._nodes)} top-level nodes]"
        ]
        for node in self._nodes:
            if isinstance(node, Parallel):
                lines.append(f"  ⇉ parallel ({node.mode.value})")
                for br in node.branches:
                    lines.append(f"     └─ {self._describe(br)}")
            elif isinstance(node, dict):
                lines.append("  ⌥ routes:")
                for route_name, body in node.items():
                    lines.append(f"     ├─ {route_name}:")
                    for sub in self._route_items(body):
                        lines.append(f"     │   → {self._describe(sub)}")
            else:
                lines.append(f"  → {self._describe(node)}")
        return "\n".join(lines)

    @staticmethod
    def _route_items(body: Any) -> list[Any]:
        if hasattr(body, "_nodes"):
            return list(body._nodes)
        if isinstance(body, list):
            return body
        return [body]

    def shutdown(self) -> None:
        self._scheduler.shutdown()

    @contextlib.asynccontextmanager
    async def _acquire_run(self, rid: str) -> AsyncIterator[None]:
        if not self._durable:
            yield
            return
        if rid in self._active_runs:
            raise RunIDInUseError(f"run_id={rid!r} is already running")
        self._active_runs.add(rid)
        try:
            yield
        finally:
            self._active_runs.discard(rid)

    async def __aenter__(self) -> Pipeline:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.shutdown()

    @staticmethod
    def _describe(fn: Any) -> str:
        name = getattr(fn, "__name__", repr(fn))
        nt = getattr(fn, "__fluxio_node_type__", NodeType.ASYNC)
        reads = getattr(fn, "__fluxio_reads__", None)
        writes = getattr(fn, "__fluxio_writes__", None)
        parts = [f"{name} ({nt.value})"]
        if reads:
            parts.append(f"reads={sorted(reads)}")
        if writes:
            parts.append(f"writes={sorted(writes)}")
        return " ".join(parts)

    def _find_step_ip(self, step_name: str) -> int:
        from fluxio.compiler.bytecode import OpCode

        for idx, instr in enumerate(self._compiled.instructions):
            if (
                instr.op == OpCode.EMIT
                and instr.event_type == "step_start"
                and instr.node_id == step_name
            ):
                return idx
        raise KeyError(f"No step {step_name!r} found in compiled pipeline")

    @staticmethod
    def _coerce_ctx(value: dict[str, Any] | Context) -> Context:
        if isinstance(value, Context):
            return value
        return Context.create(value)
