import os
import re
import sys
import time
from typing import Any
from typing import TextIO

from . import config
from . import plugin
from . import when
from .generator import AbstractTestGenerator
from .test.case import TestCase
from .third_party.colify import colified
from .third_party.color import colorize
from .util import filesystem as fs
from .util import glyphs
from .util import graph
from .util import logging
from .util.executable import Executable
from .util.parallel import starmap
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
        if root.startswith(("git@", "repo@")):
            vc, _, f = root.partition("@")
            root = f"{vc}@{os.path.abspath(f)}"
            if paths:
                raise ValueError(f"{vc}@ and paths are mutually exclusive")
        else:
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
            start = time.monotonic()
            vc: str | None = None
            if root.startswith(("git@", "repo@")):
                vc, _, root = root.partition("@")
            relroot = os.path.relpath(root, config.invocation_dir)
            logging.info(colorize("@*{Searching} %s for test generators..." % relroot), end="")
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
            elif vc is not None:
                generators = tree.setdefault(root, set())
                p_generators, p_errors = self.vcfind(root, type=vc)
                generators.update(p_generators)
                errors += p_errors
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
            dt = time.monotonic() - start
            logging.info(
                colorize("@*{Searching} %s for test generators... done (%.2fs.)" % (relroot, dt)),
                rewind=True,
            )
            logging.debug(f"Found {len(generators)} test files in {root}")
        n = sum([len(_) for _ in tree.values()])
        nr = len(tree)
        if pedantic and errors:
            raise ValueError("Stopping due to previous parsing errors")
        logging.debug(f"Found {n} test files in {nr} search roots")
        files: list[AbstractTestGenerator] = [file for files in tree.values() for file in files]
        return files

    def vcfind(self, root: str, type: str) -> tuple[list[AbstractTestGenerator], int]:
        """Find files in version control repository (only git supported)"""
        files: list[str]
        if type == "git":
            files = git_ls(root)
        elif type == "repo":
            files = repo_ls(root)
        errors: int = 0
        generators: list[AbstractTestGenerator] = []
        with fs.working_dir(root):
            gen_types = list(plugin.generators())
            for file in files:
                for gen_type in gen_types:
                    if gen_type.matches(file):
                        try:
                            generators.append(gen_type(root, file))
                        except Exception as e:
                            errors += 1
                            logging.exception(f"Failed to parse {root}/{file}", e)
                        break
        return generators, errors

    def rfind(
        self, root: str, subdir: str | None = None
    ) -> tuple[list[AbstractTestGenerator], int]:
        def skip(directory):
            if os.path.basename(directory).startswith("."):
                return True
            elif os.path.basename(directory) in self.skip_dirs:
                return True
            if os.path.exists(os.path.join(directory, ".nvtest/SESSION.TAG")):
                return True
            return False

        start = root if subdir is None else os.path.join(root, subdir)
        errors: int = 0
        gen_types = list(plugin.generators())
        generators: list[AbstractTestGenerator] = []
        for dirname, dirs, files in os.walk(start):
            if skip(dirname):
                del dirs[:]
                continue
            for f in files:
                file = os.path.join(dirname, f)
                for gen_type in gen_types:
                    if gen_type.matches(file):
                        try:
                            generator = gen_type(root, os.path.relpath(file, root))
                        except Exception as e:
                            errors += 1
                            logging.exception(f"Failed to parse {file}", e)
                        else:
                            generators.append(generator)
                        break
        return generators, errors

    @property
    def search_paths(self) -> list[str]:
        return [root for root in self.roots]

    @staticmethod
    def resolve_dependencies(cases: list[TestCase]) -> None:
        start = time.monotonic()
        logging.info(colorize("@*{Resolving} test case dependencies..."), end="")
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
        dt = time.monotonic() - start
        logging.info(
            colorize("@*{Resolving} test case dependencies... done (%.2fs.)" % dt), rewind=True
        )

    @staticmethod
    def check_for_skipped_dependencies(cases: list[TestCase]) -> None:
        start = time.monotonic()
        logging.info(colorize("@*{Checking} for skipped dependencies..."), end="")
        missing = 0
        ids = [id(case) for case in cases]
        for case in cases:
            if case.status.value in ("masked", "skipped"):
                continue
            for dep in case.dependencies:
                if id(dep) not in ids:
                    logging.error(f"ID of {dep!r} is not in test cases")
                    missing += 1
                if dep.status.value in ("masked", "skipped"):
                    case.status.set("masked", "one or more skipped dependency")
                    logging.debug(f"Dependency {dep!r} of {case!r} is marked to be skipped")
        if missing:
            raise ValueError("Missing dependencies")
        dt = time.monotonic() - start
        logging.info(
            colorize("@*{Checking} for skipped dependencies... done (%.2fs)" % dt), rewind=True
        )

    @staticmethod
    def lock_and_filter(
        generators: list[AbstractTestGenerator],
        keyword_expr: str | None = None,
        parameter_expr: str | None = None,
        on_options: list[str] | None = None,
        owners: set[str] | None = None,
        env_mods: dict[str, str] | None = None,
        regex: str | None = None,
    ) -> list[TestCase]:
        logging.info(colorize("@*{Generating} test cases..."), end="")
        locked: list[list[TestCase]]
        start = time.monotonic()
        if config.debug:
            locked = [f.lock(on_options) for f in generators]
        else:
            locked = starmap(lock_file, [(f, on_options) for f in generators])
        cases: list[TestCase] = [case for group in locked for case in group if case]
        dt = time.monotonic() - start
        nc, ng = len(cases), len(generators)
        logging.info(colorize("@*{Generating} test cases... done (%.2fs.)" % dt), rewind=True)
        logging.info(colorize("@*{Generated} %d test cases from %d generators" % (nc, ng)))

        duplicates = Finder.find_duplicates(cases)
        if duplicates:
            logging.error("Duplicate test IDs generated for the following test cases")
            for id, dcases in duplicates.items():
                logging.error(f"{id}:")
                for case in dcases:
                    logging.emit(f"  - {case.display_name}: {case.file_path}\n")
            raise ValueError("Duplicate test IDs in test suite")

        # this sanity check should not be necessary
        if any(case.status.value not in ("created", "skipped", "masked") for case in cases):
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

        masked = [case for case in cases if case.status == "masked"]
        logging.info(colorize("@*{Selected} %d test cases" % (len(cases) - len(masked))))
        if masked:
            logging.info(
                colorize("@*{Skipping} %d test cases for the following reasons:" % len(masked))
            )
            masked_reasons: dict[str, int] = {}
            for case in cases:
                if case.status.value in ("masked", "skipped"):
                    reason = str(case.status.details)
                    masked_reasons[reason] = masked_reasons.get(reason, 0) + 1
            reasons = sorted(masked_reasons, key=lambda x: masked_reasons[x])
            for reason in reversed(reasons):
                logging.emit(f"{glyphs.bullet} {masked_reasons[reason]}: {reason.lstrip()}\n")

        return cases

    @staticmethod
    def filter(
        cases: list[TestCase],
        keyword_expr: str | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        regex: str | None = None,
    ) -> None:
        def already_skipped(case: TestCase) -> bool:
            return case.status.value in ("masked", "skipped")

        rx: re.Pattern | None = None
        if regex is not None:
            logging.warning("Regular expression search can be slow for large test suites")
            rx = re.compile(regex)

        start = time.monotonic()
        logging.info(colorize("@*{Selecting} test cases based on filtering criteria..."), end="")
        owners = set(owners or [])
        for case in cases:
            try:
                config.resource_pool.satisfiable(case.required_resources())
            except config.ResourceUnsatisfiable as e:
                if not already_skipped(case):
                    s = "@*{ResourceUnsatisfiable}(%r)" % e.args[0]
                    case.status.set("masked", colorize(s))

            if not already_skipped(case) and owners:
                if not owners.intersection(case.owners):
                    case.status.set("masked", colorize("not owned by @*{%r}" % case.owners))

            if not already_skipped(case) and keyword_expr is not None:
                kwds = set(case.keywords)
                kwds.update(case.implicit_keywords)
                kwds.add(case.name)
                kwds.update(case.parameters.keys())
                match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                if not match:
                    case.status.set(
                        "masked", colorize("keyword expression @*{%r} did not match" % keyword_expr)
                    )

            if not already_skipped(case) and ("TDD" in case.keywords or "tdd" in case.keywords):
                case.status.set("masked", colorize("test marked as @*{TDD}"))

            if not already_skipped(case) and parameter_expr:
                match = when.when(
                    f"parameters={parameter_expr!r}",
                    parameters=case.parameters | case.implicit_parameters,
                )
                if not match:
                    case.status.set(
                        "masked",
                        colorize("parameter expression @*{%s} did not match" % parameter_expr),
                    )

            if not already_skipped(case) and any(
                dep.status == "masked" for dep in case.dependencies
            ):
                case.status.set("masked", colorize("one or more skipped dependencies"))

            if not already_skipped(case) and rx is not None:
                if not fs.grep(rx, case.file):
                    for asset in case.assets:
                        if os.path.isfile(asset.src):
                            if fs.grep(rx, asset.src):
                                break
                    else:
                        msg = "@*{re.search(%r) is None} evaluated to @*g{True}" % regex
                        case.status.set("masked", colorize(msg))

        dt = time.monotonic() - start
        logging.info(
            colorize("@*{Selecting} test cases based on filtering criteria... done (%.2fs.)" % dt),
            rewind=True,
        )

    @staticmethod
    def find_duplicates(cases: list[TestCase]) -> dict[str, list[TestCase]]:
        ids = [case.id for case in cases]
        duplicate_ids = {id for id in ids if ids.count(id) > 1}
        duplicates: dict[str, list[TestCase]] = {}
        for id in duplicate_ids:
            duplicates.setdefault(id, []).extend([_ for _ in cases if _.id == id])
        return duplicates

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
            file.write(cols + "\n")


def is_test_file(file: str) -> bool:
    for generator in plugin.generators():
        if generator.always_matches(file):
            return True
    return False


def find(path: str) -> AbstractTestGenerator:
    return AbstractTestGenerator.factory(path)


class FinderError(Exception):
    pass


def lock_file(file: AbstractTestGenerator, on_options: list[str] | None):
    return file.lock(on_options=on_options)


def git_ls(root: str) -> list[str]:
    git = Executable("git")
    with fs.working_dir(root):
        result = git("ls-files", "--recurse-submodules", stdout=str)
    return [f.strip() for f in result.get_output().split("\n") if f.split()]


def repo_ls(root: str) -> list[str]:
    repo = Executable("repo")
    with fs.working_dir(root):
        result = repo("-c", "git ls-files --recurse-submodules", stdout=str)
    return [f.strip() for f in result.get_output().split("\n") if f.split()]
