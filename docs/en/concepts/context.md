# Context

`Context` is the immutable, copy-on-write state threaded through every stage.

## Reading

```python
ctx.get("user_id")           # permissive — returns None if missing
ctx.get("tier", "standard")  # with default
ctx["user_id"]               # strict — raises KeyError if missing
"user_id" in ctx             # membership
```

Use `ctx[key]` when the key must exist (violation is a bug). Use `ctx.get(key)` when "missing" is a valid outcome.

## Writing

Every write returns a **new** context; the original is untouched.

```python
new_ctx = ctx.set("user", {"id": 1})
ctx.get("user")       # None — original unchanged
new_ctx.get("user")   # {"id": 1}
```

Multiple writes via `update`:

```python
ctx = ctx.update({"priority": "high", "retries": 0})
```

## Structural sharing

`Context` is backed by `pyrsistent.PMap` (a HAMT). `set()` shares unchanged sub-trees with the old context, so copies are O(log₃₂ N) in time and memory.

Forking is O(1) — it simply rewraps the same map under a new branch name.

## Forking and merging

Used internally by `Parallel` and routing:

```python
base = Context.create({"user_id": 1})
branch_a = base.fork("a").set("profile", {...})
branch_b = base.fork("b").set("orders", [...])

merged = Context.merge(base, [branch_a, branch_b])
# merged has both "profile" and "orders"
```

If two branches write the same key, `MergeConflictError` is raised with the conflicting keys and branch names.

## Snapshots

For checkpointing and debugging:

```python
data = ctx.snapshot()          # plain dict[str, Any]
ctx_ = Context.from_snapshot(data, name="restored")
```

Snapshots are what the `CheckpointStore` persists.
