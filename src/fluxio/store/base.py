from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Checkpoint:
    run_id: str
    pipeline_version: str
    ip: int
    ctx_snapshot: dict[str, Any]
    created_at: float
    meta: dict[str, Any] = field(default_factory=dict)


class CheckpointVersionError(Exception):
    pass


class CheckpointStore(ABC):
    @abstractmethod
    async def save(self, checkpoint: Checkpoint) -> None: ...

    @abstractmethod
    async def load(self, run_id: str) -> Checkpoint | None: ...

    @abstractmethod
    async def delete(self, run_id: str) -> None: ...

    @abstractmethod
    async def exists(self, run_id: str) -> bool: ...
