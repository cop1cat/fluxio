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
    """Signal a routing decision from a router stage.

    Returned (instead of a ``Context``) by a stage immediately followed by a
    ``dict`` routing block. The ``route`` selects which dict key's body to
    execute next; ``patch`` is merged into the live context as soon as the
    router returns, before the route lookup happens.
    """

    route: str
    patch: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class StageFunc(Protocol):
    """Structural protocol for any ``@stage``-decorated callable.

    All three node types satisfy this protocol — ASYNC stages are coroutines
    returning ``Context | Send``, SYNC stages are plain callables (run in a
    thread pool by the executor), and STREAM stages are async generators.
    The ``__call__`` annotation here is intentionally loose (``Any``) so the
    protocol accepts every shape; the interpreter dispatches on
    ``__fluxio_node_type__``.
    """

    __name__: str
    __fluxio_node_type__: NodeType
    __fluxio_reads__: frozenset[str] | None
    __fluxio_writes__: frozenset[str] | None
    __fluxio_input_schema__: type[BaseModel] | None
    __fluxio_output_schema__: type[BaseModel] | None
    __fluxio_timeout__: float | None

    def __call__(self, ctx: Context) -> Any: ...
