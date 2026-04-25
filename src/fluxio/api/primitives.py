from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic import BaseModel

    from fluxio.context.context import Context


class NodeType(StrEnum):
    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class ForkMode(StrEnum):
    PARALLEL = "parallel"
    FIRE_FORGET = "fire_forget"


@dataclass(frozen=True)
class Send:
    route: str
    patch: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeResult:
    ctx: Context
    duration_ms: int
    node_id: str


@runtime_checkable
class StageFunc(Protocol):
    __name__: str
    __fluxio_node_type__: NodeType
    __fluxio_reads__: frozenset[str] | None
    __fluxio_writes__: frozenset[str] | None
    __fluxio_input_schema__: type[BaseModel] | None
    __fluxio_output_schema__: type[BaseModel] | None
    __fluxio_timeout__: float | None

    async def __call__(self, ctx: Context) -> Context | Send: ...
