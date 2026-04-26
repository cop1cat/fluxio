"""Exception hierarchy for fluxio.

Every fluxio-raised exception inherits from :class:`FluxioError`, so user
code can do ``except FluxioError`` to catch any framework-originated
failure. Specific subtypes are also re-exported from the top-level
``fluxio`` package.
"""

from __future__ import annotations


class FluxioError(Exception):
    """Base class for every exception raised by fluxio itself.

    Catch this to handle any framework-originated failure without enumerating
    individual subtypes. Stage-raised exceptions (your own ``ValueError``,
    HTTP errors, etc.) propagate through unchanged and are NOT subclasses
    of this.
    """


class NoCheckpointError(FluxioError, LookupError):
    """No checkpoint exists for the requested ``run_id``.

    Raised by ``Pipeline.invoke(resume=True)``, ``Pipeline.replay``, and
    ``Pipeline.diff`` when the underlying ``CheckpointStore`` has nothing
    stored for the supplied id.
    """


class ValidationError(FluxioError):
    """Stage input or output failed Pydantic validation.

    Wraps the underlying ``pydantic.ValidationError`` (available via
    ``__cause__``) so callers get a stable, typed exception while still
    being able to introspect the field-level details.
    """
