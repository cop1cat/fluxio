# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All workflows use `uv`. Python 3.12+.

```bash
uv sync --all-extras            # install everything (redis, langfuse, dev)
uv sync --group docs            # docs deps (mkdocs + mkdocstrings + i18n)

uv run pytest                                      # all tests
uv run pytest tests/test_pipeline.py::test_name -v # single test
uv run pytest --cov=fluxio --cov-report=term       # with coverage

uv run ruff check .             # lint
uv run ruff format .            # format
uv run ty check                 # type check (uses ty, NOT mypy)

uv run mkdocs serve             # docs dev server (live reload)
uv run mkdocs build --strict    # build site (CI uses this)
```

CI is split into three workflows: `lint.yml` (ruff + ty), `ci.yml` (pytest matrix on Python 3.12 / 3.13 + Codecov), `publish.yml` (PyPI on `v*` tag), `docs.yml` (gh-pages on push to main). All must stay green.

## Architecture

fluxio is **not** a thin asyncio wrapper. It compiles a list of stages into a flat bytecode and interprets it. Understanding this requires three files together: `compiler/bytecode.py`, `compiler/compiler.py`, `runtime/interpreter.py`.

### Compile-once, interpret-many

`Pipeline.__init__` calls `Compiler().compile(nodes)` exactly once. The output is a `CompiledPipeline` containing a `tuple[Instruction, ...]` plus symbol tables (writes_map, reads_map, schemas) and a sha256 `version`. `pipe.invoke()` runs `Interpreter.run()` over those instructions with an instruction pointer.

Opcodes (in `compiler/bytecode.py`): `EMIT`, `CHECKPOINT`, `VALIDATE_INPUT`, `CALL`, `VALIDATE_OUTPUT`, `FORK`, `JOIN`, `ROUTE`, `JUMP`. **Order matters.** A normal stage compiles to: `CHECKPOINT → EMIT step_start → [VALIDATE_INPUT] → CALL → [VALIDATE_OUTPUT] → EMIT step_end`. The CHECKPOINT must come before `step_start` so durable resume replays the full stage including the start event and validation — moving it broke a regression test.

### Context as immutable HAMT

`Context` (in `context/context.py`) wraps `pyrsistent.PMap`. Every `set/update` returns a new instance with structural sharing. `_written: frozenset[str]` tracks which keys this branch wrote — used by `Context.merge()` to detect conflicts. `fork()` is O(1): same `_data`, empty `_written`, new branch name.

Two access modes by design: `ctx.get(k)` is permissive (default `None`), `ctx[k]` is strict (raises). They are not aliases.

### Parallel and routing

Both compile to bytecode tricks, not runtime branches:

- **`Parallel([a, b])`** → `EMIT branch → FORK branch_ids=(a,b) mode=PARALLEL → JOIN`. The branches' code is **not inlined** between FORK and JOIN — the interpreter looks up each branch in `symbol_table` and runs it as a single CALL via `Scheduler.run_parallel`. Each branch starts with `ctx.fork(name)`; results are merged via `Context.merge` after JOIN.
- **`{"route_a": [...], "route_b": [...]}` after a router stage** → `ROUTE route_map={name: ip} → [route_a body... JUMP continuation] → [route_b body... JUMP continuation] → continuation`. The router's `Send` is captured by `CALL` into `pending_route`, then consumed by the next `ROUTE` instruction. JUMP `target_ip` is patched after route bodies are compiled.

Auto-parallelism (`Compiler._auto_parallelize`) folds independent consecutive stages into `Parallel` blocks **only if both have declared `reads` and `writes`**. It must not fold a stage that immediately precedes a `dict` — that stage is a router and must remain adjacent to its routing block.

### Middleware chain

`MiddlewareChain` (in `runtime/middleware.py`) composes middlewares **outside-in** in declaration order. `Pipeline(middleware=[A, B, C])` calls `A → B → C → stage`. The chain wraps every `CALL`. `RetryMiddleware` and `CacheMiddleware` check `__fluxio_node_type__ == STREAM` and pass through unchanged — retry would duplicate already-emitted chunks, cache would freeze a generator. This bypass is a hard contract; tests assert it.

### Storage split

`CheckpointStore` (in `store/base.py`) and `CacheStore` (in `runtime/cache.py`) are **deliberately separate** interfaces. Don't conflate. Checkpoints carry pipeline `version` for refusing stale resumes (`CheckpointVersionError`). Cache entries are versionless and TTL-bound.

### Concurrency safety

`Pipeline._active_runs: set[str]` tracks in-flight `run_id`s for `durable=True` invocations. The check + add is atomic in a single asyncio tick (no `await` between them) — do not "improve" this with an `asyncio.Lock` and `lock.locked()`, which has a TOCTOU race that we explicitly fixed.

`pipe.stream(...)` runs the interpreter in a background `asyncio.Task` and yields chunks from a bounded `asyncio.Queue(maxsize=32)`. The consumer's `try/finally` cancels the driver and suppresses `CancelledError` on early exit — the producer must not block on `queue.put` if the consumer is gone.

## Public API surface

`src/fluxio/__init__.py` is the contract. Anything not in `__all__` is internal. Optional deps (`RedisStore`, `LangfuseCallback`, `StepHarness`, `make_ctx`) are exposed via `__getattr__` so importing `fluxio` doesn't require those extras to be installed.

`src/fluxio/py.typed` ships type info downstream (PEP 561).

## Conventions

- Annotations everywhere. `from __future__ import annotations` at the top of every module — this is enforced by ruff.
- `ty.toml` uses `possibly-unresolved-reference` — **not** `possibly-unbound` (that name was renamed in ty).
- Tests live in `tests/`, use `pytest-asyncio` with `asyncio_mode = auto` (set in `pytest.ini`). Don't add `@pytest.mark.asyncio` decorators.
- For tests that need to mock optional deps (langfuse, redis), use `monkeypatch.setitem(sys.modules, ...)` with `setattr` (`# noqa: B010`) to bypass ty's strict ModuleType attribute check.
- Docs are bilingual under `docs/en/` and `docs/ru/`. Both sides must be updated for user-facing changes. `mkdocs.yml` has separate `nav` per locale via `mkdocs-static-i18n`.
- CHANGELOG follows Keep a Changelog 1.1.0; user-visible changes go under `[Unreleased]`.

## Files to ignore

`PLAN.md` is gitignored — it was the original spec and the codebase has intentionally diverged. Don't treat it as authoritative; the README, docs, and tests are.
