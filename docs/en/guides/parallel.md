# Parallel execution

fluxio has two ways to run stages concurrently: explicit `Parallel([...])` blocks and automatic parallelization at compile time.

## Explicit `Parallel`

```python
from fluxio import Parallel

Pipeline([
    fetch_user,
    Parallel([enrich_profile, fetch_orders]),
    format_response,
])
```

Branches run concurrently via `asyncio.gather`. Each branch starts from a forked context and their writes are merged back together after all branches complete.

## Automatic parallelism

With declared reads/writes, fluxio detects independence and inserts `Parallel` blocks for you:

```python
@stage(reads=frozenset({"user_id"}), writes=frozenset({"user"}))
async def fetch_user(ctx): ...

@stage(reads=frozenset({"user_id"}), writes=frozenset({"orders"}))
async def fetch_orders(ctx): ...

Pipeline([fetch_user, fetch_orders])  # compiled as Parallel([fetch_user, fetch_orders])
```

A warning is logged so it's discoverable. Disable with `auto_parallel=False`.

## Merge conflicts

If two branches write the same key, `MergeConflictError` is raised at merge time. If writes are declared, the compiler catches the conflict during compilation instead of at runtime.

## Fire-and-forget

```python
Parallel([audit_log, metrics_push], mode=ForkMode.FIRE_FORGET)
```

Branches run concurrently but errors are only logged — they do not propagate. No merge happens; execution continues from the context before the fork.

## Tips

- Declare reads/writes. It makes intent visible, enables auto-parallelism, and catches conflicts early.
- Parallel blocks nested inside a router block (`{"premium": [Parallel([...])]}`) work as expected.
- The scheduler uses asyncio plus a thread pool; CPU-bound `SYNC` stages inside a `Parallel` really do run on multiple threads.
