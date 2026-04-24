from __future__ import annotations

import asyncio

from fluxio.store.base import Checkpoint, CheckpointStore


class InMemoryStore(CheckpointStore):
    def __init__(self) -> None:
        self._data: dict[str, Checkpoint] = {}
        self._lock = asyncio.Lock()

    async def save(self, checkpoint: Checkpoint) -> None:
        async with self._lock:
            self._data[checkpoint.run_id] = checkpoint

    async def load(self, run_id: str) -> Checkpoint | None:
        async with self._lock:
            return self._data.get(run_id)

    async def delete(self, run_id: str) -> None:
        async with self._lock:
            self._data.pop(run_id, None)

    async def exists(self, run_id: str) -> bool:
        async with self._lock:
            return run_id in self._data
