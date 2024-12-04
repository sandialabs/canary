import os
import re
import sys
from typing import Any
from typing import TextIO

from . import config
from . import plugin
from . import when
from .generator import AbstractTestGenerator
from .generator import StopRecursion
from .test.case import TestCase
from .third_party.colify import colified
from .third_party.color import colorize
from .util import filesystem as fs
from .util import graph
from .util import logging
from .util.term import terminal_size
from .util.time import hhmmss


class Finder:
    skip_dirs = ["__nvcache__", "__pycache__", ".git", ".svn", ".nvtest"]
    version_info = (1, 0, 3)

    def __init__(self) -> None:
        self.roots: dict[str, list[str] | None] = {}
        self._ready = False

    def prepare(self):
        self._ready = True

    def add(self, root: str, *paths: str, **kwargs: Any) -> None:
        tolerant: bool = kwargs.get("tolerant", False)
        if self._ready:
            raise ValueError("Cannot call add() after calling prepare()")
        root = os.path.abspath(root)
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
        tree: dict[str, set[AbstractTestGenerator]] = {}
        if not self._ready:
            raise ValueError("Cannot call discover() before calling prepare()")
        errors = 0
        for root, paths in self.roots.items():
            logging.debug(f"Searching {root} for test files")
            if os.path.isfile(root):
                try:
                    f = AbstractTestGenerator.factory(root)
                except Exception as e:
                    errors += 1
                    logging.exception(f"Failed to parse {root}", e)
                else:
                    root = f.root
                    generators = tree.setdefault(root, set())
                    generators.add(f)
            elif paths is not None:
                generators = tree.setdefault(root, set())
                for path in paths:
                    p = os.path.join(root, path)
                    if os.path.isfile(p):
                        try:
                            f = AbstractTestGenerator.factory(root, path)
                        except Exception as e:
                            errors += 1
                            logging.exception(f"Failed to parse {root}/{path}", e)
                        else:
                            generators.add(f)
                    elif os.path.isdir(p):
                        p_generators, p_errors = self.rfind(root, subdir=path)
                        generators.update(p_generators)
                        errors += p_errors
                    else:
                        errors += 1
                        logging.error(f"No such file: {path}")
            else:
                generators = tree.setdefault(root, set())
                p_generators, p_errors = self.rfind(root)
                generators.update(p_generators)
                errors += p_errors
            logging.debug(f"Found {len(generators)} test files in {root}")
        n = sum([len(_) for _ in tree.values()])
        nr = len(tree)
        if pedantic and errors:
            raise ValueError("Stopping due to previous parsing errors")
        logging.debug(f"Found {n} test files in {nr} search roots")
        files: list[AbstractTestGenerator] = [file for files in tree.values() for file in files]
        return files

    def rfind(
        self, root: str, subdir: str | None = None
    ) -> tuple[list[AbstractTestGenerator], int]:
        def skip_dir(dirname):
            if os.path.basename(dirname) in self.skip_dirs:
                return True
            if fs.is_hidden(dirname):
                return True
            if os.path.exists(os.path.join(dirname, ".nvtest")):
                return True
            return False

        start = root if subdir is None else os.path.join(root, subdir)
        paths: list[tuple[str, str]] = []
        for dirname, dirs, files in os.walk(start):
            if skip_dir(dirname):
                del dirs[:]
                continue
            for basename in files:
                file = os.path.join(dirname, basename)
                try:
                    if any(generator.matches(file) for generator in plugin.generators()):
                        paths.append((root, os.path.relpath(file, root)))
                except StopRecursion:
                    paths.append((root, os.path.relpath(file, root)))
                    del dirs[:]
                    break
        errors = 0
        generators: list[AbstractTestGenerator] = []
        for p in paths:
            try:
                generator = AbstractTestGenerator.factory(*p)
            except Exception as e:
                errors += 1
                logging.exception(f"Failed to parse {p[0]}/{p[1]}", e)
            else:
                generators.append(generator)
        return generators, errors

    @property
    def search_paths(self) -> list[str]:
        return [root for root in self.roots]

    @staticmethod
    def resolve_dependencies(cases: list[TestCase]) -> None:
        logging.debug("Resolving dependencies across test suite")
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
        logging.debug("Done resolving dependencies across test suite")

    @staticmethod
    def check_for_skipped_dependencies(cases: list[TestCase]) -> None:
        logging.debug("Validating test cases")
        missing = 0
        ids = [id(case) for case in cases]
        for case in cases:
            if case.mask:
                continue
            for dep in case.dependencies:
                if id(dep) not in ids:
                    logging.error(f"ID of {dep!r} is not in test cases")
                    missing += 1
                if dep.mask:
                    case.mask = "deselected due to skipped dependency"
                    logging.debug(f"Dependency {dep!r} of {case!r} is marked to be skipped")
        if missing:
            raise ValueError("Missing dependencies")
        logging.debug("Done validating test cases")

    @staticmethod
    def lock_and_filter(
        files: list[AbstractTestGenerator],
        keyword_expr: str | None = None,
        parameter_expr: str | None = None,
        on_options: list[str] | None = None,
        owners: set[str] | None = None,
        env_mods: dict[str, str] | None = None,
        regex: str | None = None,
    ) -> list[TestCase]:
        o = ",".join(on_options or [])
        logging.debug(
            "Creating concrete test cases using\n"
            f"    options={o}\n"
            f"    keywords={keyword_expr}\n"
            f"    parameters={parameter_expr}"
        )
        concrete_test_groups = [f.lock(on_options=on_options) for f in files]
        cases: list[TestCase] = [case for group in concrete_test_groups for case in group if case]

        # this sanity check should not be necessary
        if any(case.status.value != "created" for case in cases if not case.mask):
            raise ValueError("One or more test cases is not in created state")

        if env_mods:
            for case in cases:
                case.add_default_env(**env_mods)

        Finder.resolve_dependencies(cases)
        Finder.filter(
            cases,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        Finder.check_for_skipped_dependencies(cases)

        for p in plugin.hooks():
            for case in cases:
                p.test_discovery(case)

        logging.debug("Done creating test cases")
        return cases

    @staticmethod
    def filter(
        cases: list[TestCase],
        keyword_expr: str | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        regex: str | None = None,
    ) -> None:
        rx: re.Pattern | None = None
        if regex is not None:
            logging.warning("Regular expression search can be slow for large test suites")
            rx = re.compile(regex)

        owners = set(owners or [])
        for case in cases:
            try:
                config.resource_pool.validate(case)
            except config.ResourceUnsatisfiable as e:
                if case.mask is None:
                    s = "deselected due to @*{ResourceUnsatisfiable}(%r)" % e.args[0]
                    case.mask = colorize(s)

            if case.mask is None and owners:
                if not owners.intersection(case.owners):
                    case.mask = colorize("deselected by @*b{owner expression}")

            if case.mask is None and keyword_expr is not None:
                kwds = set(case.keywords)
                kwds.update(case.implicit_keywords)
                kwds.add(case.name)
                kwds.update(case.parameters.keys())
                match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                if not match:
                    logging.debug(f"Skipping {case}::{case.name}")
                    case.mask = colorize("deselected by @*b{keyword expression}")

            if case.mask is None and ("TDD" in case.keywords or "tdd" in case.keywords):
                case.mask = colorize("deselected due to @*b{TDD keyword}")

            if case.mask is None and parameter_expr:
                match = when.when(
                    f"parameters={parameter_expr!r}",
                    parameters=case.parameters | case.implicit_parameters,
                )
                if not match:
                    case.mask = colorize("deselected due to @*b{parameter expression}")

            if case.mask is None and any(dep.mask for dep in case.dependencies):
                case.mask = colorize("deselected due to @*b{skipped dependencies}")

            if case.mask is None and rx is not None:
                if not fs.grep(rx, case.file):
                    for asset in case.assets:
                        if os.path.isfile(asset.src):
                            if fs.grep(rx, asset.src):
                                break
                    else:
                        msg = (
                            "deselected due to @*{re.search(%r) is None} evaluated to True" % regex
                        )
                        case.mask = colorize(msg)

    @staticmethod
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

    @staticmethod
    def pprint_files(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
        for f in sorted(set([case.file for case in cases])):
            file.write(os.path.relpath(f, os.getcwd()) + "\n")

    @staticmethod
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

    @staticmethod
    def pprint_graph(cases: list[TestCase], file: TextIO = sys.stdout) -> None:
        graph.print(cases, file=file)

    @staticmethod
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
            file.write(" " + cols + "\n")
            file.write(f"found {len(lines)} test cases\n")


def is_test_file(file: str) -> bool:
    for generator in plugin.generators():
        if generator.always_matches(file):
            return True
    return False


def find(path: str) -> AbstractTestGenerator:
    return AbstractTestGenerator.factory(path)


class FinderError(Exception):
    pass
