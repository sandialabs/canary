# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import sys
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from . import config
from .generator import AbstractTestGenerator
from .third_party.colify import colified
from .third_party.color import colorize
from .util import graph
from .util import logging
from .util.term import terminal_size
from .util.time import hhmmss

if TYPE_CHECKING:
    from .testcase import TestCase
logger = logging.get_logger(__name__)


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
        if match := re.search(r"^(\w+)@(.*)", root):
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
                        logger.warning(f"{path} not found in {root}")
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
            found, e = config.pluginmanager.hook.canary_discover_generators(root=root, paths=paths)
            generators.update(found)
            errors += e
            logger.debug(f"Found {len(found)} test files in {root}")
        files: list[AbstractTestGenerator] = list(generators)
        n = len(files)
        nr = len(set(f.root for f in files))
        if pedantic and errors:
            raise ValueError("Stopping due to previous parsing errors")
        logger.debug(f"Found {n} test files in {nr} search roots")
        return files

    @property
    def search_paths(self) -> list[str]:
        return [root for root in self.roots]


def pprint_paths(cases: list["TestCase"], file: TextIO = sys.stdout) -> None:
    unique_generators: dict[str, set[str]] = dict()
    for case in cases:
        unique_generators.setdefault(case.spec.file_root, set()).add(case.spec.file_path)
    _, max_width = terminal_size()
    for root, paths in unique_generators.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        cols = colified(sorted(paths), indent=2, width=max_width)
        file.write(cols + "\n")


def pprint_files(cases: list["TestCase"], file: TextIO = sys.stdout) -> None:
    for f in sorted(set([case.spec.file for case in cases])):
        file.write("%s\n" % os.path.relpath(f, os.getcwd()))


def pprint_keywords(cases: list["TestCase"], file: TextIO = sys.stdout) -> None:
    unique_kwds: dict[str, set[str]] = dict()
    for case in cases:
        unique_kwds.setdefault(case.spec.file_root, set()).update(case.spec.keywords)
    _, max_width = terminal_size()
    for root, kwds in unique_kwds.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        cols = colified(sorted(kwds), indent=2, width=max_width)
        file.write(cols + "\n")


def pprint_graph(cases: list["TestCase"], file: TextIO = sys.stdout) -> None:
    graph.print(cases, file=file)


def pprint(cases: list["TestCase"], file: TextIO = sys.stdout) -> None:
    _, max_width = terminal_size()
    tree: dict[str, list[str]] = {}
    for case in cases:
        line = f"{hhmmss(case.spec.timeout):11s}    {case.spec.fullname}"
        tree.setdefault(case.spec.file_root, []).append(line)
    for root, lines in tree.items():
        cols = colified(lines, indent=2, width=max_width)
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        file.write(cols + "\n")


def is_test_file(file: str) -> bool:
    return config.pluginmanager.hook.canary_testcase_generator(root=file, path=None) is not None


def find(path: str) -> AbstractTestGenerator:
    return AbstractTestGenerator.factory(path)


class FinderError(Exception):
    pass


def lock_file(file: AbstractTestGenerator, on_options: list[str] | None):
    return file.lock(on_options=on_options)
