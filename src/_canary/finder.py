# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import sys
from typing import Any
from typing import TextIO

from . import config
from .generator import AbstractTestGenerator
from .test.case import TestCase
from .third_party.colify import colified
from .third_party.color import colorize
from .util import graph
from .util import logging
from .util.parallel import starmap
from .util.term import terminal_size
from .util.time import hhmmss


class Finder:
    version_info = (1, 0, 3)

    def __init__(self) -> None:
        self.roots: dict[str, list[str] | None] = {}
        self._ready = False

    def prepare(self):
        self._ready = True

    def add(self, root: str, *paths: str, **kwargs: Any) -> None:
        tolerant: bool = kwargs.get("tolerant", False)
        special: str | None = None
        if self._ready:
            raise ValueError("Cannot call add() after calling prepare()")
        if match := re.search("^(\w+)@(.*)", root):
            special, f = match.groups()
            root = os.path.abspath(f)
            if paths:
                raise ValueError(f"{special}@ and paths are mutually exclusive")
        else:
            root = os.path.abspath(root)
        if special is not None:
            if root in self.roots:
                raise ValueError(f"non-qualified root {root!r} already added to tree")
            self.roots[f"{special}@{root}"] = None
        else:
            self.roots.setdefault(root, None)
            if paths and self.roots[root] is None:
                self.roots[root] = []
            for path in paths:
                file = os.path.join(root, path)
                if not os.path.exists(file):
                    if tolerant:
                        logging.warning(f"{path} not found in {root}")
                        continue
                    else:
                        raise ValueError(f"{path} not found in {root}")
                self.roots[root].append(path)  # type: ignore

    def discover(self, pedantic: bool = True) -> list[AbstractTestGenerator]:
        if not self._ready:
            raise ValueError("Cannot call discover() before calling prepare()")
        errors: int = 0
        generators: set[AbstractTestGenerator] = set()
        for root, paths in self.roots.items():
            found, e = config.plugin_manager.hook.canary_discover_generators(root=root, paths=paths)
            generators.update(found)
            errors += e
            logging.debug(f"Found {len(found)} test files in {root}")
        files: list[AbstractTestGenerator] = list(generators)
        n = len(files)
        nr = len(set(f.root for f in files))
        if pedantic and errors:
            raise ValueError("Stopping due to previous parsing errors")
        logging.debug(f"Found {n} test files in {nr} search roots")
        return files

    @property
    def search_paths(self) -> list[str]:
        return [root for root in self.roots]


def resolve_dependencies(cases: list[TestCase]) -> None:
    ctx = logging.context(colorize("@*{Resolving} test case dependencies"))
    ctx.start()
    for case in cases:
        while True:
            if not case.unresolved_dependencies:
                break
            dep = case.unresolved_dependencies.pop(0)
            matches = dep.evaluate([c for c in cases if c != case], extra_fields=True)
            n = len(matches)
            if dep.expect == "+" and n < 1:
                raise ValueError(f"{case}: expected at least one dependency, got {n}")
            elif dep.expect == "?" and n not in (0, 1):
                raise ValueError(f"{case}: expected 0 or 1 dependency, got {n}")
            elif isinstance(dep.expect, int) and n != dep.expect:
                raise ValueError(f"{case}: expected {dep.expect} dependencies, got {n}")
            elif dep.expect != "*" and n == 0:
                raise ValueError(
                    f"Dependency pattern {dep.value} of test case {case.name} not found"
                )
            for match in matches:
                assert isinstance(match, TestCase)
                case.add_dependency(match, dep.result)
    ctx.stop()


def generate_test_cases(
    generators: list[AbstractTestGenerator],
    on_options: list[str] | None = None,
) -> list[TestCase]:
    """Generate test cases and filter based on criteria"""

    with logging.context(colorize("@*{Generating} test cases")):
        locked: list[list[TestCase]]
        if config.debug:
            locked = [f.lock(on_options) for f in generators]
        else:
            locked = starmap(lock_file, [(f, on_options) for f in generators])
        cases: list[TestCase] = [case for group in locked for case in group if case]
        nc, ng = len(cases), len(generators)
    logging.info(colorize("@*{Generated} %d test cases from %d generators" % (nc, ng)))

    duplicates = find_duplicates(cases)
    if duplicates:
        logging.error("Duplicate test IDs generated for the following test cases")
        for id, dcases in duplicates.items():
            logging.error(f"{id}:")
            for case in dcases:
                logging.emit(f"  - {case.display_name}: {case.file_path}\n")
        raise ValueError("Duplicate test IDs in test suite")

    if config.debug and any(
        not case.status.satisfies(("masked", "invalid", "created")) for case in cases
    ):
        raise ValueError("One or more test cases is not in created state")

    resolve_dependencies(cases)

    return cases


def find_duplicates(cases: list[TestCase]) -> dict[str, list[TestCase]]:
    ids = [case.id for case in cases]
    duplicate_ids = {id for id in ids if ids.count(id) > 1}
    duplicates: dict[str, list[TestCase]] = {}
    for id in duplicate_ids:
        duplicates.setdefault(id, []).extend([_ for _ in cases if _.id == id])
    return duplicates


def pprint_paths(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
    unique_generators: dict[str, set[str]] = dict()
    for case in cases:
        unique_generators.setdefault(case.file_root, set()).add(case.file_path)
    _, max_width = terminal_size()
    for root, paths in unique_generators.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        cols = colified(sorted(paths), indent=2, width=max_width)
        file.write(cols + "\n")


def pprint_files(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
    for f in sorted(set([case.file for case in cases])):
        file.write(os.path.relpath(f, os.getcwd()) + "\n")


def pprint_keywords(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
    unique_kwds: dict[str, set[str]] = dict()
    for case in cases:
        unique_kwds.setdefault(case.file_root, set()).update(case.keywords)
    _, max_width = terminal_size()
    for root, kwds in unique_kwds.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        cols = colified(sorted(kwds), indent=2, width=max_width)
        file.write(cols + "\n")


def pprint_graph(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
    graph.print(cases, file=file)


def pprint(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
    _, max_width = terminal_size()
    tree: dict[str, list[str]] = {}
    for case in cases:
        line = f"{hhmmss(case.runtime):11s}    {case.fullname}"
        tree.setdefault(case.file_root, []).append(line)
    for root, lines in tree.items():
        cols = colified(lines, indent=2, width=max_width)
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        file.write(cols + "\n")


def is_test_file(file: str) -> bool:
    for generator in config.plugin_manager.get_generators():
        if generator.always_matches(file):
            return True
    return False


def find(path: str) -> AbstractTestGenerator:
    return AbstractTestGenerator.factory(path)


class FinderError(Exception):
    pass


def lock_file(file: AbstractTestGenerator, on_options: list[str] | None):
    return file.lock(on_options=on_options)
