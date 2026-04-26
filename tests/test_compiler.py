import pytest

from fluxio import CompilationError, Parallel, stage
from fluxio.compiler.bytecode import OpCode
from fluxio.compiler.compiler import Compiler


@stage
async def a(ctx):
    return ctx.set("a", 1)


@stage
async def b(ctx):
    return ctx.set("b", 1)


def test_linear_compile():
    c = Compiler(auto_parallel=False).compile([a, b])
    ops = [i.op for i in c.instructions]
    assert ops[0] == OpCode.EMIT
    assert OpCode.CALL in ops
    assert ops[-1] == OpCode.EMIT
    assert c.version


def test_parallel_compile():
    c = Compiler(auto_parallel=False).compile([Parallel([a, b])])
    ops = [i.op for i in c.instructions]
    assert OpCode.FORK in ops
    assert OpCode.JOIN in ops


def test_write_conflict_detected():
    @stage(writes=frozenset({"x"}))
    async def w1(ctx):
        return ctx.set("x", 1)

    @stage(writes=frozenset({"x"}))
    async def w2(ctx):
        return ctx.set("x", 2)

    with pytest.raises(CompilationError):
        Compiler(auto_parallel=False).compile([Parallel([w1, w2])])


def test_auto_parallelism():
    @stage(reads=frozenset({"u"}), writes=frozenset({"p"}))
    async def p1(ctx):
        return ctx.set("p", 1)

    @stage(reads=frozenset({"u"}), writes=frozenset({"q"}))
    async def p2(ctx):
        return ctx.set("q", 1)

    c = Compiler(auto_parallel=True).compile([p1, p2])
    ops = [i.op for i in c.instructions]
    assert OpCode.FORK in ops


def test_empty_route_body_raises():
    """Regression: a route with an empty body must be a CompilationError, not a silent no-op."""
    from fluxio import Send

    @stage
    async def router(ctx):
        return Send("done")

    with pytest.raises(CompilationError, match="empty body"):
        Compiler(auto_parallel=False).compile([router, {"done": []}])
