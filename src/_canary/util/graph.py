# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
from collections import deque
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable
from typing import Sequence
from typing import TextIO

if TYPE_CHECKING:
    from ..testspec import ResolvedSpec

builtin_print = print


def static_order(specs: Sequence["ResolvedSpec"]) -> list["ResolvedSpec"]:
    map: dict[str, "ResolvedSpec"] = {}
    graph: dict[str, list[str]] = {}
    for spec in specs:
        map[spec.id] = spec
        graph[spec.id] = [dep.id for dep in spec.dependencies]
    ts = TopologicalSorter(graph)
    return [map[id] for id in ts.static_order()]


def static_order_ix(specs: Sequence["ResolvedSpec"]) -> list[int]:
    map: dict[str, int] = {}
    graph: dict[str, list[str]] = {}
    for i, spec in enumerate(specs):
        graph[spec.id] = [dep.id for dep in spec.dependencies]
        map[spec.id] = i
    ts = TopologicalSorter(graph)
    return [map[id] for id in ts.static_order()]


def print_spec(
    spec: "ResolvedSpec",
    level: int = -1,
    file=None,
    indent="",
    end=False,
):
    """Given a list of test specs, print a visual tree structure"""
    file = file or sys.stdout
    space = "    "
    branch = "│   "
    tee = "├── "
    last = "└── "

    def inner(spec: "ResolvedSpec", prefix: str = "", level=-1):
        if not level:
            return  # 0, stop iterating
        dependencies = spec.dependencies
        pointers = [tee] * (len(dependencies) - 1) + [last]
        for pointer, dependency in zip(pointers, dependencies):
            if dependency.dependencies:
                yield prefix + pointer + dependency.pretty_name
                extension = branch if pointer == tee else space
                yield from inner(dependency, prefix=prefix + extension, level=level - 1)
            else:
                yield prefix + pointer + dependency.pretty_name

    file.write(f"{tee if not end else last}{indent}{spec.pretty_name}\n")
    iterator = inner(spec, level=level)
    for line in iterator:
        file.write(f"{branch}{indent}{line}\n")


def print(specs: Sequence["ResolvedSpec"], file: str | Path | TextIO = sys.stdout) -> None:
    def streamify(arg) -> tuple[TextIO, bool]:
        if isinstance(arg, str):
            arg = Path(arg)
        if isinstance(arg, Path):
            return arg.open("w"), True
        else:
            return arg, False

    file, fown = streamify(file)
    specs = static_order(specs)  # ty: ignore[invalid-argument-type]
    all_deps = [dep for spec in specs for dep in spec.dependencies]
    remove = []
    for spec in specs:
        if spec in all_deps:
            remove.append(spec)
    specs = [spec for spec in specs if spec not in remove]
    for i, spec in enumerate(specs):
        print_spec(spec, file=file, end=i == len(specs) - 1)
    if fown:
        file.close()


def reachable_nodes(graph: dict[str, list[str]], roots: Iterable[str]) -> list[str]:
    """Return all nodes reachable from any of the given roots"""
    visited: set[str] = set()
    stack: list[str] = list(roots)
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        for dep in graph.get(node, []):
            if dep not in visited:
                stack.append(dep)
    return list(visited)


def reachable_up_down(
    graph_deps: dict[str, list[str]],
    nodes: Iterable[str],
) -> tuple[set[str], set[str]]:
    """
    graph_deps: node -> list of dependencies (A: [B,C,D] means A depends on B,C,D)
    nodes: starting nodes

    Returns (upstream, downstream):
      upstream   = all nodes that the start nodes depend on (ancestors)
      downstream = all nodes that depend on the start nodes (descendants)
    """

    # --- Convert A:[B,C] (A depends on B,C) → B:[A], C:[A]
    providers: dict = {u: set() for u in graph_deps}  # ensure all nodes present
    for u, deps in graph_deps.items():
        for d in deps:
            providers.setdefault(d, set())
            providers[d].add(u)

    start = set(nodes)

    # --- Upstream search (dependencies) ---
    # Walk backward along graph_deps edges: A -> deps
    upstream = set()
    q = deque(start)
    while q:
        u = q.popleft()
        for d in graph_deps.get(u, ()):  # dependencies of u
            if d not in upstream and d not in start:
                upstream.add(d)
                q.append(d)

    # --- Downstream search (dependents) ---
    # Walk forward along provider->consumer edges
    downstream = set()
    q = deque(start)
    while q:
        u = q.popleft()
        for v in providers.get(u, ()):  # consumers of u
            if v not in downstream and v not in start:
                downstream.add(v)
                q.append(v)

    return upstream, downstream
