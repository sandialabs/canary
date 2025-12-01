# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Sequence
from typing import TextIO
from typing import TypeVar

if TYPE_CHECKING:
    from ..testspec import ResolvedSpec
    from ..testspec import TestSpec

    SpecLike = TypeVar("SpecLike", ResolvedSpec, TestSpec)

builtin_print = print


def static_order(specs: Sequence["SpecLike"]) -> list["SpecLike"]:
    map: dict[str, "SpecLike"] = {}
    graph: dict[str, list[str]] = {}
    for spec in specs:
        map[spec.id] = spec
        graph[spec.id] = [dep.id for dep in spec.dependencies]
    ts = TopologicalSorter(graph)
    return [map[id] for id in ts.static_order()]


def static_order_ix(specs: Sequence["SpecLike"]) -> list[int]:
    map: dict[str, int] = {}
    graph: dict[str, list[str]] = {}
    for i, spec in enumerate(specs):
        graph[spec.id] = [dep.id for dep in spec.dependencies]
        map[spec.id] = i
    ts = TopologicalSorter(graph)
    return [map[id] for id in ts.static_order()]


def print_spec(
    spec: "SpecLike",
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

    def inner(spec: "SpecLike", prefix: str = "", level=-1):
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


def print(specs: Sequence["SpecLike"], file: str | Path | TextIO = sys.stdout) -> None:
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


def reachable_nodes(graph: dict[str, list[str]], roots: list[str]) -> list[str]:
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
