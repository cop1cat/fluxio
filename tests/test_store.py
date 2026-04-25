from fluxio import InMemoryStore
from fluxio.store.base import Checkpoint


async def test_save_load_delete():
    store = InMemoryStore()
    cp = Checkpoint(
        run_id="r1",
        pipeline_version="v",
        ip=3,
        ctx_snapshot={"k": 1},
        created_at=0.0,
    )
    assert not await store.exists("r1")
    await store.save(cp)
    assert await store.exists("r1")
    loaded = await store.load("r1")
    assert loaded is not None
    assert loaded.ip == 3
    await store.delete("r1")
    assert not await store.exists("r1")
