from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
import time
from typing import Any


@dataclass
class CacheEntry:
    value: dict[str, Any]
    created_at: float


class CacheStore(ABC):
    """Storage backend for CacheMiddleware. Separate from CheckpointStore."""

    @abstractmethod
    async def get(self, key: str) -> CacheEntry | None: ...

    @abstractmethod
    async def set(self, key: str, entry: CacheEntry) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...


class InMemoryCache(CacheStore):
    """Process-local cache with TTL-aware retrieval handled by CacheMiddleware."""

    def __init__(self) -> None:
        self._data: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> CacheEntry | None:
        async with self._lock:
            return self._data.get(key)

    async def set(self, key: str, entry: CacheEntry) -> None:
        async with self._lock:
            self._data[key] = entry

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)


def now() -> float:
    return time.time()
