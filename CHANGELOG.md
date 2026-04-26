# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-27

Initial public release.

### Added

- Public `Pipeline` API with `invoke`, `stream`, `run_step`, `replay`, `diff`, and `explain` methods, plus `async with Pipeline(...)` for deterministic thread-pool shutdown.
- `@stage` decorator with automatic detection of `ASYNC`, `SYNC`, and `STREAM` node types, plus options for `reads`, `writes`, `input_schema`, `output_schema`, and per-stage `timeout`.
- Immutable `Context` backed by `pyrsistent.PMap`: permissive `get`, strict `ctx[key]`, O(1) `fork`, and conflict-aware `merge` with `MergeConflictError`.
- `Parallel([...])` blocks with `PARALLEL` and `FIRE_FORGET` modes, plus auto-parallelism at compile time for stages with disjoint declared `reads` / `writes`.
- Conditional routing via `Send("route")` and `dict` blocks inside the pipeline definition; dict values accept a list of stages, a single stage, or a `Pipeline` instance.
- Durable execution with `CheckpointStore`: `InMemoryStore`, `RedisStore`. Explicit `resume=True` to continue from the last checkpoint; fresh runs by default. `CheckpointVersionError` on pipeline version mismatch and `RunIDInUseError` when a durable `invoke` is attempted with a `run_id` that is already in progress.
- Middleware chain with `RetryMiddleware`, `CacheMiddleware`, `CircuitBreakerMiddleware`, and `RateLimitMiddleware`. Retry and cache middlewares automatically bypass `STREAM` stages.
- Dedicated `CacheStore` interface with `InMemoryCache` backend, isolated from checkpoint storage.
- `BaseCallback` interface with events `on_pipeline_start/end`, `on_step_start/end`, `on_step_stream`, `on_branch`, `on_route`, `on_error`, and `on_checkpoint`. `LoggingCallback` built on the standard library logger and `LangfuseCallback` for Langfuse SDK v3 tracing.
- Pydantic `input_schema` / `output_schema` validation at stage boundaries.
- Testing utilities: `StepHarness` for isolated stage execution (with sync and async context-manager support) and `make_ctx` fixture helper.
- Bilingual (English / Russian) documentation built with MkDocs Material and `mkdocs-static-i18n`, auto-generated API reference via `mkdocstrings`, deployed to GitHub Pages on push to `main`.
- PEP 561 `py.typed` marker for downstream type checkers.
- GitHub Actions workflows: `lint.yml` (ruff + ty), `ci.yml` (pytest matrix on Python 3.12 / 3.13 with coverage uploaded to Codecov), `publish.yml` (PyPI release on `v*` tag), `docs.yml` (GitHub Pages deploy).

[0.1.0]: https://github.com/cop1cat/fluxio/releases/tag/v0.1.0
