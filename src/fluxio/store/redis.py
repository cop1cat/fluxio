from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from fluxio.store.base import Checkpoint, CheckpointStore


def _json_default(obj: Any) -> Any:
    """Best-effort fallback encoder for ctx_snapshot values.

    ``Context`` accepts arbitrary Python objects and ``InMemoryStore`` keeps
    them as-is. Redis storage requires JSON, so anything not natively
    serializable is rendered via ``str(obj)``. The round-trip is therefore
    lossy for those types — keep ctx values JSON-safe (or use a richer
    serializer) if exact round-trip matters.
    """
    return str(obj)


class RedisStore(CheckpointStore):
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        ttl: int = 86400,
        key_prefix: str = "fluxio:checkpoint",
    ) -> None:
        try:
            from redis.asyncio import from_url
        except ImportError as e:
            raise ImportError(
                "redis is required for RedisStore. Install with: pip install fluxio[redis]"
            ) from e
        self._client: Any = from_url(url, decode_responses=True)
        self._ttl = ttl
        self._prefix = key_prefix

    def _key(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}"

    async def save(self, checkpoint: Checkpoint) -> None:
        try:
            payload = json.dumps(asdict(checkpoint), default=_json_default)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Checkpoint for run_id={checkpoint.run_id!r} is not JSON-serializable "
                f"even with str() fallback: {e}. Keep ctx values JSON-safe when using RedisStore."
            ) from e
        await self._client.set(self._key(checkpoint.run_id), payload, ex=self._ttl)

    async def load(self, run_id: str) -> Checkpoint | None:
        raw = await self._client.get(self._key(run_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return Checkpoint(**data)

    async def delete(self, run_id: str) -> None:
        await self._client.delete(self._key(run_id))

    async def exists(self, run_id: str) -> bool:
        return bool(await self._client.exists(self._key(run_id)))

    async def aclose(self) -> None:
        await self._client.aclose()
