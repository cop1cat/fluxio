from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, overload

from fluxio.api.primitives import NodeType

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

    from fluxio.api.primitives import StageFunc


@overload
def stage(fn: Callable[..., Any]) -> StageFunc: ...


@overload
def stage(
    *,
    node_type: NodeType = NodeType.ASYNC,
    reads: frozenset[str] | None = None,
    writes: frozenset[str] | None = None,
    input_schema: type[BaseModel] | None = None,
    output_schema: type[BaseModel] | None = None,
    timeout: float | None = None,
) -> Callable[[Callable[..., Any]], StageFunc]: ...


def stage(
    fn: Callable[..., Any] | None = None,
    *,
    node_type: NodeType = NodeType.ASYNC,
    reads: frozenset[str] | None = None,
    writes: frozenset[str] | None = None,
    input_schema: type[BaseModel] | None = None,
    output_schema: type[BaseModel] | None = None,
    timeout: float | None = None,
) -> Any:
    """Mark a function as a pipeline stage.

    The stage type is auto-detected from the signature:

    * ``async def`` → ``ASYNC``
    * ``async def`` generator (``yield`` inside) → ``STREAM``
    * plain ``def`` → ``SYNC`` (runs in the pipeline thread pool)

    Args:
        reads / writes: Declared context keys the stage reads/writes. Enables
            auto-parallelism and write-conflict detection at compile time.
        input_schema / output_schema: Pydantic models validated against the
            context before / after the stage runs. Extra fields are ignored.
        timeout: Per-stage timeout in seconds, enforced via ``asyncio.timeout``.

    Usage::

        @stage
        async def fetch_user(ctx):
            return ctx.set("user", await db.get(ctx["user_id"]))


        @stage(reads=frozenset({"user"}), writes=frozenset({"profile"}))
        async def enrich(ctx): ...
    """

    def decorate(func: Callable[..., Any]) -> StageFunc:
        resolved = node_type
        if resolved == NodeType.ASYNC:
            if inspect.isasyncgenfunction(func):
                resolved = NodeType.STREAM
            elif not inspect.iscoroutinefunction(func):
                resolved = NodeType.SYNC

        if resolved == NodeType.STREAM and not inspect.isasyncgenfunction(func):
            raise TypeError(f"STREAM stage {func.__name__!r} must be an async generator")
        if resolved == NodeType.ASYNC and not inspect.iscoroutinefunction(func):
            raise TypeError(f"ASYNC stage {func.__name__!r} must be an async function")
        if resolved == NodeType.SYNC and (
            inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)
        ):
            raise TypeError(f"SYNC stage {func.__name__!r} must be a regular function")

        wrapped = func
        wrapped.__fluxio_node_type__ = resolved  # type: ignore[attr-defined]
        wrapped.__fluxio_reads__ = reads  # type: ignore[attr-defined]
        wrapped.__fluxio_writes__ = writes  # type: ignore[attr-defined]
        wrapped.__fluxio_input_schema__ = input_schema  # type: ignore[attr-defined]
        wrapped.__fluxio_output_schema__ = output_schema  # type: ignore[attr-defined]
        wrapped.__fluxio_timeout__ = timeout  # type: ignore[attr-defined]
        return wrapped  # type: ignore[return-value]

    if fn is not None:
        return decorate(fn)
    return decorate
