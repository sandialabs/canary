import fnmatch
import os
import sys
from typing import Any
from typing import Optional
from typing import TextIO

from . import plugin
from .generator import AbstractTestGenerator
from .resource import ResourceHandler
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
        self.roots: dict[str, Optional[list[str]]] = {}
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

    def discover(self) -> list[AbstractTestGenerator]:
        tree: dict[str, set[AbstractTestGenerator]] = {}
        if not self._ready:
            raise ValueError("Cannot call discover() before calling prepare()")
        for root, paths in self.roots.items():
            logging.debug(f"Searching {root} for test files")
            if os.path.isfile(root):
                f = AbstractTestGenerator.factory(root)
                root = f.root
                generators = tree.setdefault(root, set())
                generators.add(f)
            elif paths is not None:
                generators = tree.setdefault(root, set())
                for path in paths:
                    p = os.path.join(root, path)
                    if os.path.isfile(p):
                        generators.add(AbstractTestGenerator.factory(root, path))
                    elif os.path.isdir(p):
                        generators.update(self.rfind(root, subdir=path))
                    else:
                        raise FileNotFoundError(path)
            else:
                generators = tree.setdefault(root, set())
                generators.update(self.rfind(root))
            logging.debug(f"Found {len(generators)} test files in {root}")
        n = sum([len(_) for _ in tree.values()])
        nr = len(tree)
        logging.debug(f"Found {n} test files in {nr} search roots")
        files: list[AbstractTestGenerator] = [file for files in tree.values() for file in files]
        return files

    def rfind(self, root: str, subdir: Optional[str] = None) -> list[AbstractTestGenerator]:
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
            paths.extend(
                [
                    (root, os.path.relpath(os.path.join(dirname, f), root))
                    for f in files
                    if any([g.matches(f) for g in plugin.generators()])
                ]
            )
        generators = [AbstractTestGenerator.factory(*p) for p in paths]
        return generators

    @property
    def search_paths(self) -> list[str]:
        return [root for root in self.roots]

    @staticmethod
    def resolve_dependencies(cases: list[TestCase]) -> None:
        logging.debug("Resolving dependencies across test suite")
        case_map = {}
        for i, case in enumerate(cases):
            case_map[case.name] = i
            case_map[case.display_name] = i
            case_map[case.exec_path] = i
            d = os.path.dirname(case.exec_path)
            case_map[os.path.join(d, case.display_name)] = i
        for i, case in enumerate(cases):
            while True:
                if not case.dep_patterns:
                    break
                pat = case.dep_patterns.pop(0)
                matches = [
                    cases[k]
                    for (name, k) in case_map.items()
                    if i != k and (fnmatch.fnmatchcase(name, pat) or name == pat)
                ]
                if not matches:
                    raise ValueError(
                        f"Dependency pattern {pat!r} of test case {case.name} not found"
                    )
                for match in matches:
                    assert isinstance(match, TestCase)
                    case.add_dependency(match)
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
    def lock(
        files: list[AbstractTestGenerator],
        rh: Optional[ResourceHandler] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        owners: Optional[set[str]] = None,
        env_mods: Optional[dict[str, str]] = None,
    ) -> list[TestCase]:
        o = ",".join(on_options or [])
        logging.debug(
            "Creating concrete test cases using\n"
            f"    options={o}\n"
            f"    keywords={keyword_expr}\n"
            f"    parameters={parameter_expr}"
        )
        rh = rh or ResourceHandler()
        kwds = dict(
            cpus=rh["test:cpu_count"],
            gpus=rh["test:gpu_count"],
            nodes=rh["test:node_count"],
            keyword_expr=keyword_expr,
            timeout=rh["test:timeout"],
            parameter_expr=parameter_expr,
            on_options=on_options,
            owners=owners,
            env_mods=env_mods,
        )
        concrete_test_groups = [file.lock(**kwds) for file in files]
        cases: list[TestCase] = [case for group in concrete_test_groups for case in group if case]

        # this sanity check should not be necessary
        if any(case.status.value != "created" for case in cases if not case.mask):
            raise ValueError("One or more test cases is not in created state")

        Finder.resolve_dependencies(cases)
        Finder.check_for_skipped_dependencies(cases)

        for p in plugin.plugins():
            for case in cases:
                p.test_discovery(case)

        logging.debug("Done creating test cases")
        return cases

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
        if generator.matches(file):
            return True
    return False


def find(path: str) -> AbstractTestGenerator:
    return AbstractTestGenerator.factory(path)


class FinderError(Exception):
    pass
