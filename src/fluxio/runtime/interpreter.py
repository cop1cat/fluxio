from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from fluxio.api.primitives import ForkMode, Send
from fluxio.compiler.bytecode import OpCode
from fluxio.context.context import Context
from fluxio.errors import FluxioError, NoCheckpointError, ValidationError
from fluxio.store.base import Checkpoint, CheckpointVersionError

if TYPE_CHECKING:
    from fluxio.api.primitives import StageFunc
    from fluxio.compiler.bytecode import CompiledPipeline, Instruction
    from fluxio.observability.base import BaseCallback
    from fluxio.runtime.middleware import MiddlewareChain
    from fluxio.runtime.scheduler import Scheduler
    from fluxio.store.base import CheckpointStore

_logger = logging.getLogger("fluxio.interpreter")


async def _safe_dispatch(
    callbacks: list[BaseCallback],
    method: str,
    *args: Any,
) -> None:
    """Invoke ``method`` on every callback, swallowing and logging exceptions.

    Observability sinks (Langfuse, OTel, custom metrics) routinely have flaky
    network paths. Letting one of those failures abort the user's pipeline —
    or, worse, replace the user's stage exception with a callback exception —
    is never the right behaviour. The contract is: callbacks are best-effort,
    failures land in the ``fluxio.interpreter`` logger at WARNING level.
    """
    for cb in callbacks:
        try:
            await getattr(cb, method)(*args)
        except Exception:
            _logger.warning("Callback %s.%s raised", type(cb).__name__, method, exc_info=True)


class Interpreter:
    def __init__(
        self,
        scheduler: Scheduler,
        middleware_chain: MiddlewareChain,
    ) -> None:
        self._scheduler = scheduler
        self._chain = middleware_chain

    async def run(
        self,
        compiled: CompiledPipeline,
        ctx: Context,
        run_id: str,
        callbacks: list[BaseCallback],
        store: CheckpointStore | None = None,
        durable: bool = False,
        resume: bool = False,
    ) -> Context:
        start_ip = 0

        if resume:
            if store is None:
                raise RuntimeError("resume=True requires a checkpoint_store")
            existing = await store.load(run_id)
            if existing is None:
                raise NoCheckpointError(f"No checkpoint to resume for run_id={run_id!r}")
            if existing.pipeline_version != compiled.version:
                raise CheckpointVersionError(
                    f"Checkpoint pipeline_version={existing.pipeline_version} "
                    f"differs from current version={compiled.version}."
                )
            ctx = Context.from_snapshot(existing.ctx_snapshot, name=ctx.name)
            start_ip = existing.ip
            _logger.info("Resuming run_id=%s from ip=%d", run_id, start_ip)
        elif durable and store is not None:
            await store.delete(run_id)

        step_timers: dict[str, float] = {}
        pipeline_started_at = time.monotonic()
        instructions = compiled.instructions
        ip = start_ip
        pending_route: str | None = None
        pending_route_step: str | None = None
        try:
            while ip < len(instructions):
                instr = instructions[ip]
                op = instr.op
                if op == OpCode.EMIT:
                    await self._emit(
                        instr, run_id, ctx, callbacks, step_timers, pipeline_started_at
                    )
                elif op == OpCode.CHECKPOINT:
                    if durable and store is not None:
                        await store.save(
                            Checkpoint(
                                run_id=run_id,
                                pipeline_version=compiled.version,
                                ip=ip,
                                ctx_snapshot=ctx.snapshot(),
                                created_at=time.time(),
                            )
                        )
                        await _safe_dispatch(
                            callbacks, "on_checkpoint", run_id, instr.node_id or "?", ip
                        )
                elif op == OpCode.VALIDATE_INPUT:
                    self._validate(instr, ctx, compiled, is_input=True)
                elif op == OpCode.VALIDATE_OUTPUT:
                    self._validate(instr, ctx, compiled, is_input=False)
                elif op == OpCode.CALL:
                    assert instr.node_id is not None
                    fn = compiled.symbol_table[instr.node_id]
                    result = await self._call(instr.node_id, fn, ctx, callbacks, run_id)
                    if isinstance(result, Send):
                        ctx = ctx.update(result.patch)
                        pending_route = result.route
                        pending_route_step = instr.node_id
                    else:
                        ctx = result
                elif op == OpCode.FORK:
                    ip, ctx = await self._handle_fork(
                        instr, instructions, ip, ctx, compiled, callbacks, run_id
                    )
                    continue
                elif op == OpCode.JOIN:
                    pass
                elif op == OpCode.ROUTE:
                    if pending_route is None:
                        raise FluxioError("ROUTE instruction reached without a preceding Send")
                    await _safe_dispatch(
                        callbacks, "on_route", run_id, pending_route_step or "?", pending_route
                    )
                    ip = self._resolve_route_map(instr, pending_route)
                    pending_route = None
                    pending_route_step = None
                    continue
                elif op == OpCode.JUMP:
                    if instr.target_ip is None:
                        raise FluxioError("JUMP instruction without target_ip")
                    ip = instr.target_ip
                    continue
                ip += 1
        except Exception as e:
            step_name = self._current_step(instructions, ip)
            # Close any open step spans (e.g. when a stage timed out the
            # next instruction — its EMIT step_end — never executed) so
            # observability sinks like Langfuse don't leak unclosed spans.
            for nid, started in list(step_timers.items()):
                duration_ms = int((time.monotonic() - started) * 1000)
                await _safe_dispatch(callbacks, "on_step_end", run_id, nid, ctx, duration_ms)
                step_timers.pop(nid, None)
            await _safe_dispatch(callbacks, "on_error", run_id, step_name, e)
            # On failure we preserve the last successful CHECKPOINT untouched.
            # Resume from it replays step_start / VALIDATE_INPUT / CALL cleanly.
            raise
        if durable and store is not None:
            await store.delete(run_id)
        return ctx

    async def _emit(
        self,
        instr: Instruction,
        run_id: str,
        ctx: Context,
        callbacks: list[BaseCallback],
        step_timers: dict[str, float],
        pipeline_started_at: float,
    ) -> None:
        event = instr.event_type
        node_id = instr.node_id
        if event == "pipeline_start":
            await _safe_dispatch(callbacks, "on_pipeline_start", run_id, ctx)
        elif event == "pipeline_end":
            duration_ms = int((time.monotonic() - pipeline_started_at) * 1000)
            await _safe_dispatch(callbacks, "on_pipeline_end", run_id, ctx, duration_ms)
        elif event == "step_start" and node_id is not None:
            step_timers[node_id] = time.monotonic()
            await _safe_dispatch(callbacks, "on_step_start", run_id, node_id, ctx)
        elif event == "step_end" and node_id is not None:
            start = step_timers.pop(node_id, time.monotonic())
            duration_ms = int((time.monotonic() - start) * 1000)
            await _safe_dispatch(callbacks, "on_step_end", run_id, node_id, ctx, duration_ms)
        elif event == "branch" and instr.branch_ids is not None:
            await _safe_dispatch(callbacks, "on_branch", run_id, list(instr.branch_ids))

    def _validate(
        self,
        instr: Instruction,
        ctx: Context,
        compiled: CompiledPipeline,
        *,
        is_input: bool,
    ) -> None:
        assert instr.node_id is not None
        self._run_validation(instr.node_id, ctx, compiled, is_input=is_input)

    @staticmethod
    def _run_validation(
        node_id: str,
        ctx: Context,
        compiled: CompiledPipeline,
        *,
        is_input: bool,
    ) -> None:
        schema = (
            compiled.input_schemas.get(node_id)
            if is_input
            else compiled.output_schemas.get(node_id)
        )
        if schema is None:
            return
        try:
            schema.model_validate(ctx.snapshot())
        except Exception as e:
            kind = "Input" if is_input else "Output"
            raise ValidationError(f"{kind} validation failed for {node_id!r}: {e}") from e

    async def _call(
        self,
        node_id: str,
        fn: StageFunc,
        ctx: Context,
        callbacks: list[BaseCallback],
        run_id: str,
    ) -> Any:
        async def emit_stream(nid: str, chunk: Any) -> None:
            for cb in callbacks:
                await cb.on_step_stream(run_id, nid, chunk)

        async def terminal(f: StageFunc, c: Context) -> Any:
            return await self._scheduler.executor.run(node_id, f, c, emit_stream)

        timeout = getattr(fn, "__fluxio_timeout__", None)
        if timeout is not None:
            async with asyncio.timeout(timeout):
                return await self._chain.run(fn, ctx, terminal)
        return await self._chain.run(fn, ctx, terminal)  # type: ignore[return-value]

    async def _handle_fork(
        self,
        instr: Instruction,
        instructions: tuple[Instruction, ...],
        ip: int,
        ctx: Context,
        compiled: CompiledPipeline,
        callbacks: list[BaseCallback],
        run_id: str,
    ) -> tuple[int, Context]:
        assert instr.branch_ids is not None
        branches: list[tuple[str, StageFunc, Context]] = []
        for bid in instr.branch_ids:
            fn = compiled.symbol_table[bid]
            branches.append((bid, fn, ctx.fork(bid)))

        async def runner(fn: StageFunc, c: Context, nid: str) -> Context:
            # Each branch starts its own span. The try/finally guarantees
            # on_step_end fires even if the branch fails — otherwise sibling
            # branches that already emitted on_step_start could be cancelled
            # mid-flight by gather and leave open spans in observability
            # backends like Langfuse.
            await _safe_dispatch(callbacks, "on_step_start", run_id, nid, c)
            start = time.monotonic()
            final_ctx: Context = c
            try:
                # Branches go through CALL directly without VALIDATE_INPUT /
                # VALIDATE_OUTPUT opcodes (their bodies are not inlined into
                # the instruction stream), so re-run any declared schemas
                # explicitly here.
                self._run_validation(nid, c, compiled, is_input=True)
                result = await self._call(nid, fn, c, callbacks, run_id)
                if isinstance(result, Send):
                    raise FluxioError(
                        f"Stage {nid!r} in FORK returned Send; "
                        f"Send is not supported in parallel branches"
                    )
                self._run_validation(nid, result, compiled, is_input=False)
                final_ctx = result
                return result
            finally:
                duration_ms = int((time.monotonic() - start) * 1000)
                await _safe_dispatch(callbacks, "on_step_end", run_id, nid, final_ctx, duration_ms)

        results = await self._scheduler.run_parallel(
            branches, instr.mode or ForkMode.PARALLEL, runner
        )
        next_ip = ip + 1
        if (
            instr.mode == ForkMode.PARALLEL
            and next_ip < len(instructions)
            and instructions[next_ip].op == OpCode.JOIN
        ):
            ctx = Context.merge(ctx, results)
            next_ip += 1
        return next_ip, ctx

    @staticmethod
    def _resolve_route_map(instr: Instruction, route: str) -> int:
        if instr.route_map is None:
            raise FluxioError(f"No route_map for instruction {instr!r}")
        mapping = dict(instr.route_map)
        if route not in mapping:
            raise FluxioError(f"Unknown route {route!r} — available: {sorted(mapping.keys())}")
        return mapping[route]

    @staticmethod
    def _current_step(instructions: tuple[Instruction, ...], ip: int) -> str:
        if 0 <= ip < len(instructions):
            nid = instructions[ip].node_id
            if nid:
                return nid
        return "<pipeline>"
