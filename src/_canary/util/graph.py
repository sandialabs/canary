# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Sequence
from typing import TextIO

if TYPE_CHECKING:
    from ..test.case import TestCase

builtin_print = print


def static_order(cases: Sequence["TestCase"]) -> list["TestCase"]:
    graph: dict["TestCase", list["TestCase"]] = {}
    for case in cases:
        graph[case] = case.dependencies
    ts = TopologicalSorter(graph)
    return list(ts.static_order())


def static_order_ix(cases: Sequence["TestCase"]) -> list[int]:
    graph: dict["TestCase", list["TestCase"]] = {}
    map: dict[str, int] = {}
    for i, case in enumerate(cases):
        graph[case] = case.dependencies
        map[case.id] = i
    ts = TopologicalSorter(graph)
    return [map[case.id] for case in ts.static_order()]


def print_case(
    case: "TestCase",
    level: int = -1,
    file=None,
    indent="",
    end=False,
):
    """Given a list of test cases, print a visual tree structure"""
    file = file or sys.stdout
    space = "    "
    branch = "│   "
    tee = "├── "
    last = "└── "

    def inner(case: "TestCase", prefix: str = "", level=-1):
        if not level:
            return  # 0, stop iterating
        dependencies = case.dependencies
        pointers = [tee] * (len(dependencies) - 1) + [last]
        for pointer, dependency in zip(pointers, dependencies):
            if dependency.dependencies:
                yield prefix + pointer + dependency.pretty_repr()
                extension = branch if pointer == tee else space
                yield from inner(dependency, prefix=prefix + extension, level=level - 1)
            else:
                yield prefix + pointer + dependency.pretty_repr()

    file.write(f"{tee if not end else last}{indent}{case.pretty_repr()}\n")
    iterator = inner(case, level=level)
    for line in iterator:
        file.write(f"{branch}{indent}{line}\n")


def print(cases: list["TestCase"], file: str | Path | TextIO = sys.stdout) -> None:
    def streamify(arg) -> tuple[TextIO, bool]:
        if isinstance(arg, str):
            arg = Path(arg)
        if isinstance(arg, Path):
            return arg.open("w"), True
        else:
            return arg, False

    file, fown = streamify(file)
    cases = static_order(cases)
    all_deps = [dep for case in cases for dep in case.dependencies]
    remove = []
    for case in cases:
        if case in all_deps:
            remove.append(case)
    cases = [case for case in cases if case not in remove]
    for i, case in enumerate(cases):
        print_case(case, file=file, end=i == len(cases) - 1)
    if fown:
        file.close()
