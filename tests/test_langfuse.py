import sys
import types
from typing import ClassVar

import pytest

from fluxio import Pipeline, stage


class _FakeSpan:
    def __init__(self, name: str, log: list) -> None:
        self.name = name
        self.log = log
        log.append(("start", name))

    def start_span(self, name: str) -> "_FakeSpan":
        return _FakeSpan(name, self.log)

    def update(self, **kwargs) -> None:
        self.log.append(("update", self.name, kwargs))

    def end(self) -> None:
        self.log.append(("end", self.name))


class _FakeLangfuse:
    instances: ClassVar[list["_FakeLangfuse"]] = []

    def __init__(self, **_) -> None:
        self.log: list = []
        _FakeLangfuse.instances.append(self)

    def start_span(self, name: str) -> _FakeSpan:
        return _FakeSpan(name, self.log)


@pytest.fixture
def fake_langfuse(monkeypatch):
    fake_module = types.ModuleType("langfuse")
    setattr(fake_module, "Langfuse", _FakeLangfuse)  # noqa: B010
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)
    _FakeLangfuse.instances.clear()
    yield _FakeLangfuse


async def test_langfuse_emits_spans_for_pipeline(fake_langfuse):
    from fluxio.observability.langfuse import LangfuseCallback

    @stage
    async def a(ctx):
        return ctx.set("x", 1)

    @stage
    async def b(ctx):
        return ctx.set("y", 2)

    cb = LangfuseCallback(public_key="pk", secret_key="sk")
    async with Pipeline([a, b], callbacks=[cb], auto_parallel=False) as pipe:
        await pipe.invoke({}, run_id="run-lf")

    [instance] = fake_langfuse.instances
    events = instance.log
    names_started = [n for (e, n, *_) in events if e == "start"]
    names_ended = [n for (e, n, *_) in events if e == "end"]
    assert names_started == ["run-lf", "a", "b"]
    assert set(names_ended) == {"run-lf", "a", "b"}
