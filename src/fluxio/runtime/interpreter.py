from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from fluxio.api.primitives import ForkMode, Send
from fluxio.compiler.bytecode import CompiledPipeline, Instruction, OpCode
from fluxio.context.context import Context
from fluxio.runtime.middleware import MiddlewareChain
from fluxio.store.base import Checkpoint, CheckpointVersionError

if TYPE_CHECKING:
    from fluxio.api.primitives import StageFunc
    from fluxio.observability.base import BaseCallback
    from fluxio.runtime.scheduler import Scheduler
    from fluxio.store.base import CheckpointStore

_logger = logging.getLogger("fluxio.interpreter")


class Interpreter:
    def __init__(
        self,
        scheduler: "Scheduler",
        middleware_chain: MiddlewareChain,
    ) -> None:
        self._scheduler = scheduler
        self._chain = middleware_chain

    async def run(
        self,
        compiled: CompiledPipeline,
        ctx: Context,
        run_id: str,
        callbacks: list["BaseCallback"],
        store: "CheckpointStore | None" = None,
        durable: bool = False,
        force_restart: bool = False,
    ) -> Context:
        start_ip = 0

        if durable and store is not None and not force_restart:
            existing = await store.load(run_id)
            if existing is not None:
                if existing.pipeline_version != compiled.version:
                    raise CheckpointVersionError(
                        f"Checkpoint pipeline_version={existing.pipeline_version} "
                        f"differs from current version={compiled.version}. "
                        "Pass force_restart=True to ignore."
                    )
                ctx = Context.from_snapshot(existing.ctx_snapshot, name=ctx.name)
                start_ip = existing.ip
                _logger.info("Resuming run_id=%s from ip=%d", run_id, start_ip)

        pipeline_start = time.monotonic()
        step_timers: dict[str, float] = {}
        instructions = compiled.instructions
        ip = start_ip
        pending_route: str | None = None
        try:
            while ip < len(instructions):
                instr = instructions[ip]
                op = instr.op
                if op == OpCode.EMIT:
                    await self._emit(instr, run_id, ctx, callbacks, step_timers)
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
                        for cb in callbacks:
                            await cb.on_checkpoint(
                                run_id, instr.node_id or "?", ip
                            )
                elif op == OpCode.VALIDATE_INPUT:
                    self._validate(instr, ctx, compiled, input=True)
                elif op == OpCode.VALIDATE_OUTPUT:
                    self._validate(instr, ctx, compiled, input=False)
                elif op == OpCode.CALL:
                    assert instr.node_id is not None
                    fn = compiled.symbol_table[instr.node_id]
                    result = await self._call(instr.node_id, fn, ctx, callbacks, run_id)
                    if isinstance(result, Send):
                        ctx = ctx.update(result.patch)
                        pending_route = result.route
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
                        raise RuntimeError(
                            "ROUTE instruction reached without a preceding Send"
                        )
                    ip = self._resolve_route_map(instr, pending_route)
                    pending_route = None
                    continue
                elif op == OpCode.JUMP:
                    if instr.target_ip is None:
                        raise RuntimeError("JUMP instruction without target_ip")
                    ip = instr.target_ip
                    continue
                ip += 1
        except Exception as e:
            step_name = self._current_step(instructions, ip)
            for cb in callbacks:
                await cb.on_error(run_id, step_name, e)
            if durable and store is not None:
                await store.save(
                    Checkpoint(
                        run_id=run_id,
                        pipeline_version=compiled.version,
                        ip=ip,
                        ctx_snapshot=ctx.snapshot(),
                        created_at=time.time(),
                        error=True,
                    )
                )
            raise
        duration = int((time.monotonic() - pipeline_start) * 1000)
        if durable and store is not None:
            await store.delete(run_id)
        return ctx

    async def _emit(
        self,
        instr: Instruction,
        run_id: str,
        ctx: Context,
        callbacks: list["BaseCallback"],
        step_timers: dict[str, float],
    ) -> None:
        event = instr.event_type
        node_id = instr.node_id
        for cb in callbacks:
            if event == "pipeline_start":
                await cb.on_pipeline_start(run_id, ctx)
            elif event == "pipeline_end":
                await cb.on_pipeline_end(run_id, ctx, 0)
            elif event == "step_start" and node_id is not None:
                step_timers[node_id] = time.monotonic()
                await cb.on_step_start(run_id, node_id, ctx)
            elif event == "step_end" and node_id is not None:
                start = step_timers.pop(node_id, time.monotonic())
                await cb.on_step_end(
                    run_id, node_id, ctx, int((time.monotonic() - start) * 1000)
                )
            elif event == "branch" and instr.branch_ids is not None:
                await cb.on_branch(run_id, list(instr.branch_ids))

    def _validate(
        self,
        instr: Instruction,
        ctx: Context,
        compiled: CompiledPipeline,
        input: bool,
    ) -> None:
        assert instr.node_id is not None
        schema = (
            compiled.input_schemas.get(instr.node_id)
            if input
            else compiled.output_schemas.get(instr.node_id)
        )
        if schema is None:
            return
        try:
            schema.model_validate(ctx.snapshot())
        except Exception as e:
            raise RuntimeError(
                f"{'Input' if input else 'Output'} validation failed for "
                f"{instr.node_id!r}: {e}"
            ) from e

    async def _call(
        self,
        node_id: str,
        fn: "StageFunc",
        ctx: Context,
        callbacks: list["BaseCallback"],
        run_id: str,
    ) -> Any:
        async def emit_stream(nid: str, chunk: Any) -> None:
            for cb in callbacks:
                await cb.on_step_stream(run_id, nid, chunk)

        async def terminal(f: "StageFunc", c: Context) -> Any:
            return await self._scheduler.executor.run(node_id, f, c, emit_stream)

        return await self._chain.run(fn, ctx, terminal)  # type: ignore[return-value]

    async def _handle_fork(
        self,
        instr: Instruction,
        instructions: tuple[Instruction, ...],
        ip: int,
        ctx: Context,
        compiled: CompiledPipeline,
        callbacks: list["BaseCallback"],
        run_id: str,
    ) -> tuple[int, Context]:
        assert instr.branch_ids is not None
        branches: list[tuple[str, StageFunc, Context]] = []
        for bid in instr.branch_ids:
            fn = compiled.symbol_table[bid]
            branches.append((bid, fn, ctx.fork(bid)))

        async def runner(fn: "StageFunc", c: Context, nid: str) -> Context:
            for cb in callbacks:
                await cb.on_step_start(run_id, nid, c)
            start = time.monotonic()
            result = await self._call(nid, fn, c, callbacks, run_id)
            if isinstance(result, Send):
                raise RuntimeError(
                    f"Stage {nid!r} in FORK returned Send; not supported in parallel branches"
                )
            for cb in callbacks:
                await cb.on_step_end(
                    run_id, nid, result, int((time.monotonic() - start) * 1000)
                )
            return result

        results = await self._scheduler.run_parallel(branches, instr.mode or ForkMode.PARALLEL, runner)
        next_ip = ip + 1
        if instr.mode == ForkMode.PARALLEL:
            if next_ip < len(instructions) and instructions[next_ip].op == OpCode.JOIN:
                ctx = Context.merge(ctx, results)
                next_ip += 1
        return next_ip, ctx

    @staticmethod
    def _resolve_route_map(instr: Instruction, route: str) -> int:
        if instr.route_map is None:
            raise RuntimeError(f"No route_map for instruction {instr!r}")
        mapping = dict(instr.route_map)
        if route not in mapping:
            raise RuntimeError(f"Unknown route {route!r} in route_map")
        return mapping[route]

    @staticmethod
    def _current_step(instructions: tuple[Instruction, ...], ip: int) -> str:
        if 0 <= ip < len(instructions):
            nid = instructions[ip].node_id
            if nid:
                return nid
        return "<pipeline>"
