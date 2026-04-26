from fluxio.api.parallel import Parallel
from fluxio.api.pipeline import Pipeline, RunIDInUseError
from fluxio.api.primitives import ForkMode, NodeType, Send
from fluxio.api.stage import stage
from fluxio.compiler.compiler import CompilationError
from fluxio.context.context import Context, MergeConflictError
from fluxio.errors import FluxioError, NoCheckpointError, ValidationError
from fluxio.observability.base import BaseCallback
from fluxio.observability.logging import LoggingCallback
from fluxio.runtime.cache import CacheStore, InMemoryCache
from fluxio.runtime.middleware import (
    CacheMiddleware,
    CircuitBreakerMiddleware,
    CircuitOpenError,
    Middleware,
    RateLimitMiddleware,
    RetryMiddleware,
)
from fluxio.store.base import CheckpointVersionError
from fluxio.store.memory import InMemoryStore

__all__ = [
    "BaseCallback",
    "CacheMiddleware",
    "CacheStore",
    "CheckpointVersionError",
    "CircuitBreakerMiddleware",
    "CircuitOpenError",
    "CompilationError",
    "Context",
    "FluxioError",
    "ForkMode",
    "InMemoryCache",
    "InMemoryStore",
    "LoggingCallback",
    "MergeConflictError",
    "Middleware",
    "NoCheckpointError",
    "NodeType",
    "Parallel",
    "Pipeline",
    "RateLimitMiddleware",
    "RetryMiddleware",
    "RunIDInUseError",
    "Send",
    "ValidationError",
    "stage",
]


def __getattr__(name: str) -> object:
    if name == "RedisStore":
        from fluxio.store.redis import RedisStore

        return RedisStore
    if name == "LangfuseCallback":
        from fluxio.observability.langfuse import LangfuseCallback

        return LangfuseCallback
    if name == "StepHarness":
        from fluxio.testing.harness import StepHarness

        return StepHarness
    if name == "make_ctx":
        from fluxio.testing.fixtures import make_ctx

        return make_ctx
    raise AttributeError(
        f"module 'fluxio' has no attribute {name!r}. "
        f"Optional names exposed via extras: RedisStore (fluxio[redis]), "
        f"LangfuseCallback (fluxio[langfuse]), StepHarness, make_ctx."
    )
