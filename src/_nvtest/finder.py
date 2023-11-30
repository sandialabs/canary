import fnmatch
import os
import re
from typing import Optional

from . import config
from .test import AbstractTestFile
from .test import TestCase
from .util import filesystem as fs
from .util import tty


class Finder:
    skip_dirs = ["__pycache__", ".git", ".svn", ".nvtest"]
    version_info = (1, 0, 3)

    def __init__(self) -> None:
        self.roots: dict[str, Optional[list[str]]] = {}
        self._ready = False
        self.tree: dict[str, set[AbstractTestFile]] = {}

    def prepare(self):
        self._ready = True

    def add(self, root: str, *paths: str) -> None:
        if self._ready:
            raise ValueError("Cannot call add() after calling prepare()")
        root = os.path.abspath(root)
        self.roots.setdefault(root, None)
        if paths and self.roots[root] is None:
            self.roots[root] = []
        for path in paths:
            file = os.path.join(root, path)
            if not os.path.exists(file):
                raise ValueError(f"{path} not found in {root}")
            self.roots[root].append(path)  # type: ignore

    def populate(self) -> dict[str, set[AbstractTestFile]]:
        if len(self.tree):
            raise ValueError("populate() should be called one time")
        if not self._ready:
            raise ValueError("Cannot call populate() before calling prepare()")
        for root, paths in self.roots.items():
            tty.verbose(f"Searching {root} for test files")
            if os.path.isfile(root):
                f = AbstractTestFile(root)
                root = f.root
                testfiles = self.tree.setdefault(root, set())
                testfiles.add(f)
            elif paths is not None:
                testfiles = self.tree.setdefault(root, set())
                for path in paths:
                    p = os.path.join(root, path)
                    if os.path.isfile(p):
                        testfiles.add(AbstractTestFile(root, path))
                    elif os.path.isdir(p):
                        testfiles.update(self.rfind(root, subdir=path))
                    else:
                        raise FileNotFoundError(path)
            else:
                testfiles = self.tree.setdefault(root, set())
                testfiles.update(self.rfind(root))
            tty.verbose(f"Found {len(testfiles)} test files in {root}")
        n = sum([len(_) for _ in self.tree.values()])
        nr = len(self.tree)
        tty.verbose(f"Found {n} test files in {nr} search roots")
        return self.tree

    def rfind(self, root: str, subdir: Optional[str] = None) -> list[AbstractTestFile]:
        testfiles: list[AbstractTestFile] = []

        def skip_dir(dirname):
            if os.path.basename(dirname) in self.skip_dirs:
                return True
            if fs.is_hidden(dirname):
                return True
            if os.path.exists(os.path.join(dirname, ".nvtest")):
                return True
            return False

        start = root if subdir is None else os.path.join(root, subdir)
        for dirname, dirs, files in os.walk(start):
            if skip_dir(dirname):
                del dirs[:]
                continue
            paths = [
                os.path.relpath(os.path.join(dirname, f), root)
                for f in files
                if is_test_file(f)
            ]
            testfiles.extend([AbstractTestFile(root, path) for path in paths])
        return testfiles

    @property
    def search_paths(self) -> list[str]:
        return [root for root in self.roots]

    @staticmethod
    def resolve_dependencies(cases: list[TestCase]) -> None:
        tty.verbose("Resolving dependencies across test suite")
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
        tty.verbose("Done resolving dependencies across test suite")

    @staticmethod
    def check_for_skipped_dependencies(cases: list[TestCase]) -> None:
        tty.verbose("Validating test cases")
        missing = 0
        ids = [id(case) for case in cases]
        for case in cases:
            if case.skip:
                continue
            for dep in case.dependencies:
                if id(dep) not in ids:
                    tty.error(f"ID of {dep!r} is not in test cases")
                    missing += 1
                if dep.skip:
                    case.skip = "deselected due to skipped dependency"
                    tty.warn(f"Dependency {dep!r} of {case!r} is marked to be skipped")
        if missing:
            raise ValueError("Missing dependencies")
        tty.verbose("Done validating test cases")

    @staticmethod
    def freeze(
        tree: dict[str, set[AbstractTestFile]],
        cpu_count: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
    ) -> list[TestCase]:
        cases: list[TestCase] = []
        o = ",".join(on_options or [])
        tty.verbose(
            "Creating concrete test cases using",
            f"options={o}",
            f"keywords={keyword_expr}",
        )
        for abstract_files in tree.values():
            for abstract_file in abstract_files:
                concrete_test_cases = abstract_file.freeze(
                    cpu_count=cpu_count,
                    keyword_expr=keyword_expr,
                    parameter_expr=parameter_expr,
                    on_options=on_options,
                )
                cases.extend([case for case in concrete_test_cases if case])
        Finder.resolve_dependencies(cases)
        Finder.check_for_skipped_dependencies(cases)
        tty.verbose("Done creating test cases")
        return cases


def is_test_file(file):
    file_pattern = config.get("config:test_files") or r"^[a-zA-Z_]\w*\.(vvt|pyt)$"
    return bool(re.search(file_pattern, os.path.basename(file)))


class FinderError(Exception):
    pass
