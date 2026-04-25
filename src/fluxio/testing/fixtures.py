from __future__ import annotations

from typing import Any

from fluxio.context.context import Context


def make_ctx(data: dict[str, Any] | None = None, name: str = "test") -> Context:
    return Context.create(data, name=name)
