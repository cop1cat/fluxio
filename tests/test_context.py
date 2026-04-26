import pytest

from fluxio import Context, MergeConflictError


def test_get_set_immutable():
    a = Context.create({"x": 1})
    b = a.set("y", 2)
    assert a.get("x") == 1
    assert a.get("y") is None
    assert b.get("y") == 2
    assert b.get("x") == 1


def test_strict_getitem_raises():
    c = Context.create({"x": 1})
    assert c["x"] == 1
    with pytest.raises(KeyError):
        c["missing"]


def test_get_custom_default():
    c = Context.create()
    assert c.get("missing", 42) == 42


def test_fork_shares_data_resets_written():
    base = Context.create({"k": "v"})
    f = base.fork("branch1")
    assert f.get("k") == "v"
    assert f._written == frozenset()
    assert f.name == "branch1"


def test_merge_combines_disjoint_writes():
    base = Context.create({"a": 1})
    b1 = base.fork("b1").set("x", 10)
    b2 = base.fork("b2").set("y", 20)
    m = Context.merge(base, [b1, b2])
    assert m.get("x") == 10
    assert m.get("y") == 20
    assert m.get("a") == 1


def test_merge_conflict_raises():
    base = Context.create({})
    b1 = base.fork("b1").set("k", 1)
    b2 = base.fork("b2").set("k", 2)
    with pytest.raises(MergeConflictError):
        Context.merge(base, [b1, b2])


def test_snapshot_roundtrip():
    c = Context.create({"a": 1, "b": [1, 2]})
    snap = c.snapshot()
    restored = Context.from_snapshot(snap)
    assert restored.get("a") == 1
    assert restored.get("b") == [1, 2]


def test_snapshot_is_deep_copy():
    """Mutating a value returned by snapshot() must not corrupt the live Context."""
    original = Context.create({"items": [1, 2], "config": {"key": "v"}})
    snap = original.snapshot()
    snap["items"].append(99)
    snap["config"]["key"] = "tampered"
    assert original["items"] == [1, 2]
    assert original["config"] == {"key": "v"}


def test_from_snapshot_preserves_written_when_passed():
    """Cached parallel-branch results must round-trip the write set."""
    base = Context.create({"x": 0})
    branch = base.fork("b").set("x", 10).set("y", 20)
    snap = branch.snapshot()
    restored = Context.from_snapshot(snap, name="b", written=frozenset(branch._written))
    merged = Context.merge(base, [restored])
    assert merged["x"] == 10
    assert merged["y"] == 20
