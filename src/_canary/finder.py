# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
from typing import TYPE_CHECKING
from typing import Any

from . import config
from .generator import AbstractTestGenerator
from .util import logging

if TYPE_CHECKING:
    pass
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


def is_test_file(file: str) -> bool:
    return config.pluginmanager.hook.canary_testcase_generator(root=file, path=None) is not None


class FinderError(Exception):
    pass


def lock_file(file: AbstractTestGenerator, on_options: list[str] | None):
    return file.lock(on_options=on_options)
