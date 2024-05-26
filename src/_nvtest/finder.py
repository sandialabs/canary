import fnmatch
import os
import sys
from itertools import repeat
from typing import Any
from typing import Optional
from typing import TextIO

from . import plugin
from .test.case import TestCase
from .test.generator import TestGenerator
from .third_party.colify import colified
from .third_party.color import colorize
from .util import filesystem as fs
from .util import graph
from .util import logging
from .util import parallel
from .util.resource import ResourceInfo
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

    def discover(self) -> list[TestGenerator]:
        tree: dict[str, set[TestGenerator]] = {}
        if not self._ready:
            raise ValueError("Cannot call populate() before calling prepare()")
        for root, paths in self.roots.items():
            logging.debug(f"Searching {root} for test files")
            if os.path.isfile(root):
                f = self.gen_factory(root)
                root = f.root
                generators = tree.setdefault(root, set())
                generators.add(f)
            elif paths is not None:
                generators = tree.setdefault(root, set())
                for path in paths:
                    p = os.path.join(root, path)
                    if os.path.isfile(p):
                        generators.add(self.gen_factory(root, path))
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
        files: list[TestGenerator] = [file for files in tree.values() for file in files]
        return files

    def rfind(self, root: str, subdir: Optional[str] = None) -> list[TestGenerator]:
        def skip_dir(dirname):
            if os.path.basename(dirname) in self.skip_dirs:
                return True
            if fs.is_hidden(dirname):
                return True
            if os.path.exists(os.path.join(dirname, ".nvtest")):
                return True
            return False

        file_types = tuple([_.file_type for _ in plugin.test_generators()])
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
                    if f.endswith(file_types)
                ]
            )
        generators: list[TestGenerator] = parallel.starmap(self.gen_factory, paths)

        return generators

    def gen_factory(self, root: str, path: Optional[str] = None) -> TestGenerator:
        for factory in plugin.test_generators():
            if factory.matches(root if path is None else path):
                return factory(root, path=path)
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"No test generator for {f}")

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
    def freeze(
        files: list[TestGenerator],
        resourceinfo: Optional[ResourceInfo] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        owners: Optional[set[str]] = None,
    ) -> list[TestCase]:
        o = ",".join(on_options or [])
        logging.debug(
            "Creating concrete test cases using\n"
            f"    options={o}\n"
            f"    keywords={keyword_expr}\n"
            f"    parameters={parameter_expr}"
        )
        resourceinfo = resourceinfo or ResourceInfo()
        kwds = dict(
            cpus=resourceinfo["test:cpus"],
            gpus=resourceinfo["test:gpus"],
            keyword_expr=keyword_expr,
            timelimit=resourceinfo["test:timeout"],
            parameter_expr=parameter_expr,
            on_options=on_options,
            owners=owners,
        )
        args = list(zip(files, repeat(kwds, len(files))))
        concrete_test_groups: list[list[TestCase]] = parallel.starmap(freeze_abstract_file, args)
        cases: list[TestCase] = [case for group in concrete_test_groups for case in group if case]

        # this sanity check should not be necessary
        if any(case.status.value != "created" for case in cases if not case.mask):
            raise ValueError("One or more test cases is not in created state")

        for hook in plugin.plugins("test", "discovery"):
            for case in cases:
                hook(case)

        Finder.resolve_dependencies(cases)
        Finder.check_for_skipped_dependencies(cases)

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
            unique_kwds.setdefault(case.file_root, set()).update(case.keywords())
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
    file_types = tuple([_.file_type for _ in plugin.test_generators()])
    return file.endswith(file_types)


def freeze_abstract_file(file: TestGenerator, kwds: dict) -> list[TestCase]:
    concrete_test_cases: list[TestCase] = file.freeze(**kwds)
    return concrete_test_cases


def find(path: str) -> TestGenerator:
    for factory in plugin.test_generators():
        if factory.matches(path):
            return factory(path)
    raise TypeError(f"No test generator for {path}")


class FinderError(Exception):
    pass
