# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Topologically-ordered dependency graph organized into parallel levels.

``LevelGraph`` groups items into levels where all dependencies of an item
appear in earlier levels, enabling safe parallel execution within each level.
Key factory methods are ``from_items`` and ``from_levels``; ``project``
extracts sub-graphs.
"""

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
    """Immutable directed acyclic graph whose nodes are grouped into dependency levels.

    Nodes within the same level have no dependency relationship and can be
    processed concurrently. Each level comes strictly after all levels that
    contain its dependencies.

    Attributes:
        items_by_id: Mapping from node ID to node object.
        deps_by_id: Mapping from node ID to the IDs of its direct dependencies.
        dependents_by_id: Mapping from node ID to the IDs of nodes that depend on it.
        level_ids: Tuple of levels, each a tuple of node IDs in that level.
    """

    items_by_id: dict[str, T]
    deps_by_id: dict[str, tuple[str, ...]]
    dependents_by_id: dict[str, tuple[str, ...]]
    level_ids: tuple[tuple[str, ...], ...]

    @classmethod
    def empty(cls) -> "LevelGraph[T]":
        """Return an empty ``LevelGraph`` with no nodes."""
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
        """Build a ``LevelGraph`` from a flat sequence of items.

        Args:
            items: The nodes to include in the graph.
            id_fn: Callable that returns a unique string ID for each item.
            deps_fn: Callable that returns the dependency IDs for each item.
            sort_key: Optional key function for deterministic ordering within each level.
            require_closed: If ``True``, raise ``ValueError`` when a dependency ID
                is not present in ``items``.

        Returns:
            A fully constructed ``LevelGraph``.

        Raises:
            ValueError: On duplicate IDs, missing dependencies (if ``require_closed``),
                or dependency cycles.
        """
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
        """Build a ``LevelGraph`` from pre-partitioned levels, validating consistency.

        Args:
            levels: Sequence of sequences where each inner sequence is one level.
            id_fn: Callable that returns a unique string ID for each item.
            deps_fn: Callable that returns the dependency IDs for each item.
            require_closed: If ``True``, raise ``ValueError`` for missing dependency IDs.

        Returns:
            A ``LevelGraph`` with the provided level partitioning.

        Raises:
            ValueError: If the provided levels are inconsistent with the computed dependencies.
        """
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
        """Return the graph nodes grouped into their dependency levels."""
        return tuple(
            tuple(self.items_by_id[item_id] for item_id in level) for level in self.level_ids
        )

    def topo_order(self) -> Iterator[T]:
        """Yield all items in topological (level-by-level) order."""
        for level in self.levels:
            yield from level

    def __iter__(self) -> Iterator[T]:
        return self.topo_order()

    def __len__(self) -> int:
        return len(self.items_by_id)

    def ids(self) -> list[str]:
        """Return all node IDs in topological order."""
        return [item_id for level in self.level_ids for item_id in level]

    def dependencies_of(self, item_id: str) -> tuple[T, ...]:
        """Return the direct dependencies of ``item_id``.

        Args:
            item_id: ID of the node whose dependencies to retrieve.

        Returns:
            Tuple of dependency node objects.
        """
        return tuple(self.items_by_id[dep_id] for dep_id in self.deps_by_id[item_id])

    def dependents_of(self, item_id: str) -> tuple[T, ...]:
        """Return the nodes that directly depend on ``item_id``.

        Args:
            item_id: ID of the node whose dependents to retrieve.

        Returns:
            Tuple of dependent node objects.
        """
        return tuple(self.items_by_id[user_id] for user_id in self.dependents_by_id[item_id])

    def roots(self) -> list[T]:
        """Return nodes with no dependencies (sources of the DAG)."""
        return [self.items_by_id[item_id] for item_id, deps in self.deps_by_id.items() if not deps]

    def leaves(self) -> list[T]:
        """Return nodes that no other node depends on (sinks of the DAG)."""
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
        """Return a sub-graph containing only the specified nodes and optionally their transitive neighborhood.

        Args:
            ids: Node IDs to include in the projection.
            include_upstreams: Also include all transitive dependencies of ``ids``.
            include_downstreams: Also include all transitive dependents of ``ids``.
            require_closed: If ``True``, raise when a retained dependency is absent.
            sort_key: Optional key for stable level ordering in the projection.

        Returns:
            A new ``LevelGraph`` restricted to the selected nodes.
        """
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
        """Build a new graph from a subset of this graph's items, reusing stored deps."""
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
        """Assert that ``level_ids`` is a valid level partition for this graph's deps."""
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
    """Invert a dependency mapping to produce a dependents mapping."""
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
    """Topologically sort ``deps_by_id`` into parallel levels using graphlib.

    Returns:
        Tuple of levels, each a tuple of node IDs ready to process simultaneously.
    """
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
