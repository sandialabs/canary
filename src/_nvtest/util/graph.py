import sys
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TextIO
from typing import Union

from ..test import TestCase

builtin_print = print


def static_order(cases: list[TestCase]) -> list[TestCase]:
    graph: dict[TestCase, set[TestCase]] = {}
    for case in cases:
        graph[case] = case.dependencies
    ts = TopologicalSorter(graph)
    return list(ts.static_order())


def print_case(
    case: TestCase,
    level: int = -1,
    file=None,
    indent="",
):
    """Given a list of test cases, print a visual tree structure"""
    file = file or sys.stdout
    space = "    "
    branch = "│   "
    tee = "├── "
    last = "└── "

    def inner(case: TestCase, prefix: str = "", level=-1):
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

    file.write(f"{tee}{indent}{case.pretty_repr()}\n")
    iterator = inner(case, level=level)
    for line in iterator:
        file.write(f"{branch}{indent}{line}\n")


def print(cases: list[TestCase], file: Union[str, Path, TextIO] = sys.stdout) -> None:
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
    for case in cases:
        print_case(case, file=file)
    if fown:
        file.close()
