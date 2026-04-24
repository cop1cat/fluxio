from fluxio.api.parallel import Parallel
from fluxio.api.pipeline import Pipeline
from fluxio.api.primitives import ForkMode, NodeResult, NodeType, Send
from fluxio.api.stage import stage
from fluxio.compiler.compiler import CompilationError
from fluxio.context.context import Context, MergeConflictError
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
from fluxio.store.memory import InMemoryStore

__all__ = [
    "BaseCallback",
    "CacheMiddleware",
    "CacheStore",
    "CircuitBreakerMiddleware",
    "CircuitOpenError",
    "CompilationError",
    "Context",
    "ForkMode",
    "InMemoryCache",
    "InMemoryStore",
    "LoggingCallback",
    "MergeConflictError",
    "Middleware",
    "NodeResult",
    "NodeType",
    "Parallel",
    "Pipeline",
    "RateLimitMiddleware",
    "RetryMiddleware",
    "Send",
    "stage",
]


def __getattr__(name: str) -> object:
    if name == "RedisStore":
        from fluxio.store.redis import RedisStore

        return RedisStore
    if name == "StepHarness":
        from fluxio.testing.harness import StepHarness

        return StepHarness
    if name == "make_ctx":
        from fluxio.testing.fixtures import make_ctx

        return make_ctx
    raise AttributeError(name)
