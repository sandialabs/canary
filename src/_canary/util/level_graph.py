# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
from graphlib import CycleError
from graphlib import TopologicalSorter
from typing import Any
from typing import Callable
from typing import Generic
from typing import Iterable
from typing import Iterator
from typing import Sequence
from typing import TypeVar

T = TypeVar("T")

IdFn = Callable[[T], str]
DepsFn = Callable[[T], Iterable[str]]
SortKey = Callable[[T], Any]


@dataclasses.dataclass(frozen=True)
class LevelGraph(Generic[T]):
    items_by_id: dict[str, T]
    deps_by_id: dict[str, tuple[str, ...]]
    dependents_by_id: dict[str, tuple[str, ...]]
    level_ids: tuple[tuple[str, ...], ...]

    @classmethod
    def empty(cls) -> "LevelGraph[T]":
        return cls(items_by_id={}, deps_by_id={}, dependents_by_id={}, level_ids=())

    @classmethod
    def from_items(
        cls,
        items: Sequence[T],
        *,
        id_fn: IdFn[T],
        deps_fn: DepsFn[T],
        sort_key: SortKey[T] | None = None,
        require_closed: bool = True,
    ) -> "LevelGraph[T]":
        items_by_id: dict[str, T] = {}

        for item in items:
            item_id = id_fn(item)
            if item_id in items_by_id:
                raise ValueError(f"Duplicate graph node ID: {item_id}")
            items_by_id[item_id] = item

        known_ids = set(items_by_id)

        deps_by_id: dict[str, tuple[str, ...]] = {}

        for item in items:
            item_id = id_fn(item)
            deps: list[str] = []

            for dep_id in deps_fn(item):
                if dep_id not in known_ids:
                    if require_closed:
                        raise ValueError(f"{item_id}: dependency {dep_id} is not present in graph")
                    continue
                deps.append(dep_id)

            deps_by_id[item_id] = tuple(deps)

        dependents_by_id = _build_dependents(deps_by_id)

        try:
            level_ids = _build_levels(deps_by_id, items_by_id=items_by_id, sort_key=sort_key)
        except CycleError as e:
            raise ValueError("Dependency cycle detected") from e

        return cls(
            items_by_id=items_by_id,
            deps_by_id=deps_by_id,
            dependents_by_id=dependents_by_id,
            level_ids=level_ids,
        )

    @classmethod
    def from_levels(
        cls,
        levels: Sequence[Sequence[T]],
        *,
        id_fn: IdFn[T],
        deps_fn: DepsFn[T],
        require_closed: bool = True,
    ) -> "LevelGraph[T]":
        items = [item for level in levels for item in level]

        graph = cls.from_items(items, id_fn=id_fn, deps_fn=deps_fn, require_closed=require_closed)

        provided_level_ids = tuple(tuple(id_fn(item) for item in level) for level in levels)

        graph._validate_level_ids(provided_level_ids)

        return cls(
            items_by_id=graph.items_by_id,
            deps_by_id=graph.deps_by_id,
            dependents_by_id=graph.dependents_by_id,
            level_ids=provided_level_ids,
        )

    @property
    def levels(self) -> tuple[tuple[T, ...], ...]:
        return tuple(
            tuple(self.items_by_id[item_id] for item_id in level) for level in self.level_ids
        )

    def topo_order(self) -> Iterator[T]:
        for level in self.levels:
            yield from level

    def __iter__(self) -> Iterator[T]:
        return self.topo_order()

    def __len__(self) -> int:
        return len(self.items_by_id)

    def ids(self) -> list[str]:
        return [item_id for level in self.level_ids for item_id in level]

    def dependencies_of(self, item_id: str) -> tuple[T, ...]:
        return tuple(self.items_by_id[dep_id] for dep_id in self.deps_by_id[item_id])

    def dependents_of(self, item_id: str) -> tuple[T, ...]:
        return tuple(self.items_by_id[user_id] for user_id in self.dependents_by_id[item_id])

    def roots(self) -> list[T]:
        return [self.items_by_id[item_id] for item_id, deps in self.deps_by_id.items() if not deps]

    def leaves(self) -> list[T]:
        return [
            self.items_by_id[item_id]
            for item_id, users in self.dependents_by_id.items()
            if not users
        ]

    def project(
        self,
        ids: Iterable[str],
        *,
        include_upstreams: bool = False,
        include_downstreams: bool = False,
        require_closed: bool = True,
        sort_key: SortKey[T] | None = None,
    ) -> "LevelGraph[T]":
        selected = set(ids)

        if include_upstreams:
            stack = list(selected)
            while stack:
                item_id = stack.pop()
                for dep_id in self.deps_by_id.get(item_id, ()):
                    if dep_id not in selected:
                        selected.add(dep_id)
                        stack.append(dep_id)

        if include_downstreams:
            stack = list(selected)
            while stack:
                item_id = stack.pop()
                for user_id in self.dependents_by_id.get(item_id, ()):
                    if user_id not in selected:
                        selected.add(user_id)
                        stack.append(user_id)

        items = [self.items_by_id[item_id] for item_id in selected]

        # Reuse stored deps instead of requiring original dep extraction.
        return self._from_projected_items(items, require_closed=require_closed, sort_key=sort_key)

    def _from_projected_items(
        self, items: Sequence[T], *, require_closed: bool, sort_key: SortKey[T] | None
    ) -> "LevelGraph[T]":
        selected_ids = {item_id for item_id, item in self.items_by_id.items() if item in items}

        items_by_id = {item_id: self.items_by_id[item_id] for item_id in selected_ids}

        deps_by_id: dict[str, tuple[str, ...]] = {}

        for item_id in selected_ids:
            deps: list[str] = []
            for dep_id in self.deps_by_id[item_id]:
                if dep_id not in selected_ids:
                    if require_closed:
                        raise ValueError(
                            f"{item_id}: dependency {dep_id} is not present in projected graph"
                        )
                    continue
                deps.append(dep_id)
            deps_by_id[item_id] = tuple(deps)

        dependents_by_id = _build_dependents(deps_by_id)
        level_ids = _build_levels(deps_by_id, items_by_id=items_by_id, sort_key=sort_key)

        return LevelGraph(
            items_by_id=items_by_id,
            deps_by_id=deps_by_id,
            dependents_by_id=dependents_by_id,
            level_ids=level_ids,
        )

    def _validate_level_ids(self, level_ids: tuple[tuple[str, ...], ...]) -> None:
        level_of: dict[str, int] = {}

        for level_index, level in enumerate(level_ids):
            for item_id in level:
                if item_id in level_of:
                    raise ValueError(f"Duplicate item ID in levels: {item_id}")
                level_of[item_id] = level_index

        if set(level_of) != set(self.items_by_id):
            missing = set(self.items_by_id) - set(level_of)
            extra = set(level_of) - set(self.items_by_id)
            raise ValueError(f"Level graph mismatch: missing={missing}, extra={extra}")

        for item_id, dep_ids in self.deps_by_id.items():
            item_level = level_of[item_id]
            for dep_id in dep_ids:
                dep_level = level_of[dep_id]
                if dep_level >= item_level:
                    raise ValueError(
                        f"Invalid level graph: {item_id} depends on {dep_id}, "
                        f"but dependency is not in an earlier level"
                    )


def _build_dependents(deps_by_id: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    dependents: dict[str, list[str]] = {item_id: [] for item_id in deps_by_id}

    for item_id, dep_ids in deps_by_id.items():
        for dep_id in dep_ids:
            dependents.setdefault(dep_id, []).append(item_id)

    return {item_id: tuple(users) for item_id, users in dependents.items()}


def _build_levels(
    deps_by_id: dict[str, tuple[str, ...]],
    *,
    items_by_id: dict[str, T],
    sort_key: SortKey[T] | None,
) -> tuple[tuple[str, ...], ...]:
    sorter = TopologicalSorter(deps_by_id)
    sorter.prepare()

    levels: list[tuple[str, ...]] = []

    while sorter.is_active():
        ready = list(sorter.get_ready())

        if sort_key is not None:
            ready.sort(key=lambda item_id: sort_key(items_by_id[item_id]))
        else:
            ready.sort()

        levels.append(tuple(ready))
        sorter.done(*ready)

    return tuple(levels)
