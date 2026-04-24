from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from fluxio.api.parallel import Parallel
from fluxio.api.primitives import ForkMode, NodeType
from fluxio.compiler.bytecode import CompiledPipeline, Instruction, OpCode

if TYPE_CHECKING:
    from pydantic import BaseModel

    from fluxio.api.primitives import StageFunc

_logger = logging.getLogger("fluxio.compiler")


class CompilationError(Exception):
    def __init__(self, message: str, node_ids: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.node_ids = node_ids or []


Node = Any


class Compiler:
    def __init__(self, auto_parallel: bool = True) -> None:
        self._auto_parallel = auto_parallel

    def compile(self, nodes: list[Node]) -> CompiledPipeline:
        instructions: list[Instruction] = []
        symbol_table: dict[str, StageFunc] = {}
        writes_map: dict[str, frozenset[str]] = {}
        reads_map: dict[str, frozenset[str]] = {}
        input_schemas: dict[str, type[BaseModel]] = {}
        output_schemas: dict[str, type[BaseModel]] = {}

        instructions.append(Instruction(op=OpCode.EMIT, event_type="pipeline_start"))

        normalized = self._auto_parallelize(nodes) if self._auto_parallel else list(nodes)

        i = 0
        while i < len(normalized):
            node = normalized[i]
            if isinstance(node, Parallel):
                self._compile_parallel(
                    node,
                    instructions,
                    symbol_table,
                    writes_map,
                    reads_map,
                    input_schemas,
                    output_schemas,
                )
                i += 1
            elif isinstance(node, dict):
                raise CompilationError(
                    "Route dict must follow a router stage, not be the first node"
                )
            else:
                if i + 1 < len(normalized) and isinstance(normalized[i + 1], dict):
                    self._compile_router_block(
                        node,
                        normalized[i + 1],
                        instructions,
                        symbol_table,
                        writes_map,
                        reads_map,
                        input_schemas,
                        output_schemas,
                    )
                    i += 2
                else:
                    self._compile_stage(
                        node,
                        instructions,
                        symbol_table,
                        writes_map,
                        reads_map,
                        input_schemas,
                        output_schemas,
                    )
                    i += 1

        instructions.append(Instruction(op=OpCode.EMIT, event_type="pipeline_end"))

        frozen = tuple(instructions)
        version = hashlib.sha256(repr(frozen).encode()).hexdigest()[:16]
        return CompiledPipeline(
            instructions=frozen,
            symbol_table=symbol_table,
            writes_map=writes_map,
            reads_map=reads_map,
            input_schemas=input_schemas,
            output_schemas=output_schemas,
            version=version,
        )

    def _compile_stage(
        self,
        fn: StageFunc,
        instructions: list[Instruction],
        symbol_table: dict[str, StageFunc],
        writes_map: dict[str, frozenset[str]],
        reads_map: dict[str, frozenset[str]],
        input_schemas: dict[str, type[BaseModel]],
        output_schemas: dict[str, type[BaseModel]],
    ) -> None:
        node_id = self._node_id(fn, symbol_table)
        self._register(
            node_id,
            fn,
            symbol_table,
            writes_map,
            reads_map,
            input_schemas,
            output_schemas,
        )
        # CHECKPOINT before step_start so that resume replays the full stage
        # (step_start EMIT, input validation, and CALL) from the saved ip.
        instructions.append(Instruction(op=OpCode.CHECKPOINT, node_id=node_id))
        instructions.append(Instruction(op=OpCode.EMIT, event_type="step_start", node_id=node_id))
        if node_id in input_schemas:
            instructions.append(Instruction(op=OpCode.VALIDATE_INPUT, node_id=node_id))
        instructions.append(Instruction(op=OpCode.CALL, node_id=node_id))
        if node_id in output_schemas:
            instructions.append(Instruction(op=OpCode.VALIDATE_OUTPUT, node_id=node_id))
        instructions.append(Instruction(op=OpCode.EMIT, event_type="step_end", node_id=node_id))

    def _compile_router_block(
        self,
        router: StageFunc,
        routes: dict[str, Any],
        instructions: list[Instruction],
        symbol_table: dict[str, StageFunc],
        writes_map: dict[str, frozenset[str]],
        reads_map: dict[str, frozenset[str]],
        input_schemas: dict[str, type[BaseModel]],
        output_schemas: dict[str, type[BaseModel]],
    ) -> None:
        self._compile_stage(
            router,
            instructions,
            symbol_table,
            writes_map,
            reads_map,
            input_schemas,
            output_schemas,
        )
        route_map_ips: dict[str, int] = {}
        route_ip_placeholder = len(instructions)
        instructions.append(Instruction(op=OpCode.ROUTE, route_map=()))

        jump_positions: list[int] = []
        for route_name, body in routes.items():
            route_map_ips[route_name] = len(instructions)
            sub_nodes = self._unwrap_route_body(body)
            normalized = self._auto_parallelize(sub_nodes) if self._auto_parallel else sub_nodes
            for sub in normalized:
                if isinstance(sub, Parallel):
                    self._compile_parallel(
                        sub,
                        instructions,
                        symbol_table,
                        writes_map,
                        reads_map,
                        input_schemas,
                        output_schemas,
                    )
                else:
                    self._compile_stage(
                        sub,
                        instructions,
                        symbol_table,
                        writes_map,
                        reads_map,
                        input_schemas,
                        output_schemas,
                    )
            jump_positions.append(len(instructions))
            instructions.append(Instruction(op=OpCode.JUMP, target_ip=-1))

        continuation_ip = len(instructions)
        instructions[route_ip_placeholder] = Instruction(
            op=OpCode.ROUTE,
            route_map=tuple(route_map_ips.items()),
        )
        for pos in jump_positions:
            instructions[pos] = Instruction(op=OpCode.JUMP, target_ip=continuation_ip)

    @staticmethod
    def _unwrap_route_body(body: Any) -> list[Any]:
        if hasattr(body, "_nodes"):
            return list(body._nodes)
        if isinstance(body, list):
            return body
        return [body]

    def _compile_parallel(
        self,
        block: Parallel,
        instructions: list[Instruction],
        symbol_table: dict[str, StageFunc],
        writes_map: dict[str, frozenset[str]],
        reads_map: dict[str, frozenset[str]],
        input_schemas: dict[str, type[BaseModel]],
        output_schemas: dict[str, type[BaseModel]],
    ) -> None:
        branch_ids: list[str] = []
        declared_writes: dict[str, frozenset[str]] = {}
        for branch_fn in block.branches:
            nid = self._node_id(branch_fn, symbol_table)
            branch_ids.append(nid)
            self._register(
                nid,
                branch_fn,
                symbol_table,
                writes_map,
                reads_map,
                input_schemas,
                output_schemas,
            )
            w = getattr(branch_fn, "__fluxio_writes__", None)
            if w:
                declared_writes[nid] = w

        self._check_write_conflicts(declared_writes)

        instructions.append(
            Instruction(op=OpCode.EMIT, event_type="branch", branch_ids=tuple(branch_ids))
        )
        instructions.append(
            Instruction(
                op=OpCode.FORK,
                branch_ids=tuple(branch_ids),
                mode=block.mode,
            )
        )
        if block.mode == ForkMode.PARALLEL:
            instructions.append(Instruction(op=OpCode.JOIN))

    def _auto_parallelize(self, nodes: list[Node]) -> list[Node]:
        result: list[Node] = []
        i = 0
        while i < len(nodes):
            current = nodes[i]
            if isinstance(current, Parallel | dict):
                result.append(current)
                i += 1
                continue
            # Do not fold a stage that is immediately followed by a route dict —
            # that stage is the router and must remain adjacent to the dict.
            next_is_dict = i + 1 < len(nodes) and isinstance(nodes[i + 1], dict)
            if next_is_dict:
                result.append(current)
                i += 1
                continue
            group: list[Node] = [current]
            j = i + 1
            while j < len(nodes) and not isinstance(nodes[j], Parallel | dict):
                candidate = nodes[j]
                # Stop before a router: the stage at j must stay next to the dict at j+1.
                if j + 1 < len(nodes) and isinstance(nodes[j + 1], dict):
                    break
                if self._independent(group, candidate):
                    group.append(candidate)
                    j += 1
                else:
                    break
            if len(group) > 1:
                _logger.debug(
                    "auto-parallelized independent stages: %s",
                    [getattr(n, "__name__", repr(n)) for n in group],
                )
                result.append(Parallel(branches=group))
            else:
                result.append(current)
            i = j if len(group) > 1 else i + 1
        return result

    @staticmethod
    def _independent(group: list[Node], candidate: Node) -> bool:
        c_reads = getattr(candidate, "__fluxio_reads__", None)
        c_writes = getattr(candidate, "__fluxio_writes__", None)
        if c_reads is None or c_writes is None:
            return False
        for existing in group:
            e_reads = getattr(existing, "__fluxio_reads__", None)
            e_writes = getattr(existing, "__fluxio_writes__", None)
            if e_reads is None or e_writes is None:
                return False
            if e_writes & c_reads or c_writes & e_reads or e_writes & c_writes:
                return False
        return True

    @staticmethod
    def _check_write_conflicts(
        declared_writes: dict[str, frozenset[str]],
    ) -> None:
        items = list(declared_writes.items())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a_id, a_w = items[i]
                b_id, b_w = items[j]
                overlap = a_w & b_w
                if overlap:
                    raise CompilationError(
                        f"Write conflict between {a_id!r} and {b_id!r} on keys {sorted(overlap)}",
                        node_ids=[a_id, b_id],
                    )

    @staticmethod
    def _node_id(fn: Any, symbol_table: dict[str, Any]) -> str:
        base = getattr(fn, "__name__", None) or repr(fn)
        if base not in symbol_table:
            return base
        if symbol_table[base] is fn:
            return base
        n = 2
        while f"{base}#{n}" in symbol_table:
            n += 1
        return f"{base}#{n}"

    @staticmethod
    def _register(
        node_id: str,
        fn: Any,
        symbol_table: dict[str, StageFunc],
        writes_map: dict[str, frozenset[str]],
        reads_map: dict[str, frozenset[str]],
        input_schemas: dict[str, type[BaseModel]],
        output_schemas: dict[str, type[BaseModel]],
    ) -> None:
        if not hasattr(fn, "__fluxio_node_type__"):
            raise CompilationError(f"Object {fn!r} is not a @stage — missing __fluxio_node_type__")
        if fn.__fluxio_node_type__ == NodeType.STREAM:
            pass
        symbol_table[node_id] = fn
        w = getattr(fn, "__fluxio_writes__", None)
        if w:
            writes_map[node_id] = w
        r = getattr(fn, "__fluxio_reads__", None)
        if r:
            reads_map[node_id] = r
        isch = getattr(fn, "__fluxio_input_schema__", None)
        if isch:
            input_schemas[node_id] = isch
        osch = getattr(fn, "__fluxio_output_schema__", None)
        if osch:
            output_schemas[node_id] = osch
