from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fluxio.api.primitives import ForkMode

if TYPE_CHECKING:
    from fluxio.api.primitives import StageFunc


@dataclass
class Parallel:
    branches: list[StageFunc]
    mode: ForkMode = ForkMode.PARALLEL
    name: str | None = None
