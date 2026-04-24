from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyrsistent import PMap, pmap

_MISSING: Any = object()


class MergeConflictError(Exception):
    def __init__(self, conflicting_keys: list[str], branch_names: list[str]) -> None:
        self.conflicting_keys = conflicting_keys
        self.branch_names = branch_names
        super().__init__(
            f"Merge conflict on keys {conflicting_keys} across branches {branch_names}"
        )


@dataclass(frozen=True)
class Context:
    _data: PMap = field(default_factory=pmap)
    _written: frozenset[str] = field(default_factory=frozenset)
    name: str = "root"

    @staticmethod
    def create(
        initial: dict[str, Any] | None = None,
        name: str = "root",
    ) -> Context:
        data = pmap(initial) if initial else pmap()
        return Context(_data=data, _written=frozenset(), name=name)

    def get(self, key: str, default: Any = _MISSING) -> Any:
        if key in self._data:
            return self._data[key]
        if default is _MISSING:
            raise KeyError(key)
        return default

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def set(self, key: str, value: Any) -> Context:
        return Context(
            _data=self._data.set(key, value),
            _written=self._written | {key},
            name=self.name,
        )

    def update(self, patch: dict[str, Any]) -> Context:
        if not patch:
            return self
        new_data = self._data
        for k, v in patch.items():
            new_data = new_data.set(k, v)
        return Context(
            _data=new_data,
            _written=self._written | set(patch.keys()),
            name=self.name,
        )

    def fork(self, branch_name: str) -> Context:
        return Context(_data=self._data, _written=frozenset(), name=branch_name)

    @staticmethod
    def merge(base: Context, branches: list[Context]) -> Context:
        seen: dict[str, str] = {}
        conflicts: list[str] = []
        conflict_branches: list[str] = []
        merged_data = base._data
        merged_written = set(base._written)
        for branch in branches:
            for key in branch._written:
                if key in seen and seen[key] != branch.name:
                    if key not in conflicts:
                        conflicts.append(key)
                        conflict_branches.extend([seen[key], branch.name])
                    continue
                seen[key] = branch.name
                merged_data = merged_data.set(key, branch._data[key])
                merged_written.add(key)
        if conflicts:
            raise MergeConflictError(conflicts, list(dict.fromkeys(conflict_branches)))
        return Context(
            _data=merged_data,
            _written=frozenset(merged_written),
            name=base.name,
        )

    def snapshot(self) -> dict[str, Any]:
        return dict(self._data)

    @staticmethod
    def from_snapshot(data: dict[str, Any], name: str = "restored") -> Context:
        return Context(_data=pmap(data), _written=frozenset(), name=name)
