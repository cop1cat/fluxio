import sys
import types

import pytest


class _FakeRedisAsync:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.closed = False

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.data
        self.data.pop(key, None)
        return int(existed)

    async def exists(self, key: str) -> int:
        return int(key in self.data)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_redis(monkeypatch):
    asyncio_mod = types.ModuleType("redis.asyncio")
    client = _FakeRedisAsync()

    def from_url(url: str, decode_responses: bool = False):
        return client

    setattr(asyncio_mod, "from_url", from_url)  # noqa: B010
    root = types.ModuleType("redis")
    setattr(root, "asyncio", asyncio_mod)  # noqa: B010
    monkeypatch.setitem(sys.modules, "redis", root)
    monkeypatch.setitem(sys.modules, "redis.asyncio", asyncio_mod)
    yield client


async def test_redis_store_roundtrip(fake_redis):
    from fluxio.store.base import Checkpoint
    from fluxio.store.redis import RedisStore

    store = RedisStore(url="redis://test", ttl=60)
    cp = Checkpoint(
        run_id="r1",
        pipeline_version="v",
        ip=5,
        ctx_snapshot={"a": 1},
        created_at=0.0,
    )
    assert not await store.exists("r1")
    await store.save(cp)
    assert await store.exists("r1")
    assert fake_redis.data["fluxio:checkpoint:r1"]

    loaded = await store.load("r1")
    assert loaded is not None
    assert loaded.ip == 5
    assert loaded.ctx_snapshot == {"a": 1}

    await store.delete("r1")
    assert not await store.exists("r1")

    await store.aclose()
    assert fake_redis.closed is True
