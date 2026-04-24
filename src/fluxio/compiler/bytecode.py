from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from fluxio.api.primitives import ForkMode

if TYPE_CHECKING:
    from pydantic import BaseModel

    from fluxio.api.primitives import StageFunc


class OpCode(StrEnum):
    CALL = "call"
    FORK = "fork"
    JOIN = "join"
    ROUTE = "route"
    VALIDATE_INPUT = "validate_input"
    VALIDATE_OUTPUT = "validate_output"
    EMIT = "emit"
    CHECKPOINT = "checkpoint"


@dataclass(frozen=True)
class Instruction:
    op: OpCode
    node_id: str | None = None
    branch_ids: tuple[str, ...] | None = None
    mode: ForkMode | None = None
    event_type: str | None = None
    route_map: tuple[tuple[str, int], ...] | None = None


@dataclass(frozen=True)
class CompiledPipeline:
    instructions: tuple[Instruction, ...]
    symbol_table: dict[str, "StageFunc"] = field(default_factory=dict)
    writes_map: dict[str, frozenset[str]] = field(default_factory=dict)
    reads_map: dict[str, frozenset[str]] = field(default_factory=dict)
    input_schemas: dict[str, "type[BaseModel]"] = field(default_factory=dict)
    output_schemas: dict[str, "type[BaseModel]"] = field(default_factory=dict)
    version: str = ""
