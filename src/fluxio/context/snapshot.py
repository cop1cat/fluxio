from __future__ import annotations

from typing import Any

from fluxio.context.context import Context


def dump(ctx: Context) -> dict[str, Any]:
    return ctx.snapshot()


def load(data: dict[str, Any], name: str = "restored") -> Context:
    return Context.from_snapshot(data, name=name)
