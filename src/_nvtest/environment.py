import errno
import fnmatch
import os
from typing import Optional

from .config import Config
from .test import AbstractTestFile
from .test import TestCase
from .util import filesystem as fs
from .util import tty


class Environment:
    _config_file = "environ"
    exts = (".pyt", ".vvt")
    skip_dirs = ["__pycache__", ".git", ".svn"]
    version_info = (1, 0, 3)

    def __init__(self, search_paths: Optional[list[str]] = None) -> None:
        self.dir = os.getcwd()
        self._search_paths: list[str] = []
        for path in search_paths or [self.dir]:
            if not os.path.exists(path):
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
            self._search_paths.append(os.path.relpath(os.path.abspath(path), self.dir))
        self.tree: dict[str, list[AbstractTestFile]] = {}

    def asdict(self):
        data = dict(vars(self))
        data.pop("tree")
        return data

    def expandpath(self, path):
        return os.path.normpath(os.path.join(self.dir, path))

    @property
    def search_paths(self) -> list[str]:
        return [self.expandpath(p) for p in self._search_paths]

    def discover(self) -> None:
        tty.verbose("Discovering tests")
        for root in self.search_paths:
            tty.verbose(f"Searching for tests in {root}")
            testfiles: list[AbstractTestFile] = []
            root = os.path.abspath(root)
            tty.verbose(f"Searching {root} for test files")
            if os.path.isfile(root):
                testfiles.append(AbstractTestFile(root))
                continue
            for dirname, dirs, files in os.walk(root):
                if os.path.basename(dirname) in self.skip_dirs or fs.is_hidden(dirname):
                    del dirs[:]
                    continue
                paths = [
                    os.path.relpath(os.path.join(dirname, f), root)
                    for f in files
                    if f.endswith(self.exts)
                ]
                testfiles.extend([AbstractTestFile(root, path) for path in paths])
            self.tree[root] = testfiles
            tty.verbose(f"Found {len(testfiles)} test files in {root}")
        n = sum(len(_) for _ in self.tree.values())
        tty.verbose(f"Found {n} test files in {len(self.tree)} search roots")

    def test_cases(
        self,
        config: Config,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
    ) -> list[TestCase]:
        cases: list[TestCase] = []
        o = ",".join(on_options or [])
        tty.verbose(
            "Creating concrete test cases using",
            f"options={o}",
            f"keywords={keyword_expr}",
        )
        for abstract_files in self.tree.values():
            for abstract_file in abstract_files:
                concrete_test_cases = abstract_file.freeze(
                    config, keyword_expr=keyword_expr, on_options=on_options
                )
                cases.extend([case for case in concrete_test_cases if case])
        self.resolve_dependencies(cases)
        self.check_for_skipped_dependencies(cases)
        tty.verbose("Done creating test cases")
        return cases

    def resolve_dependencies(self, cases: list[TestCase]) -> None:
        tty.verbose("Resolving dependencies across test suite")
        case_map = dict([(case.name, i) for (i, case) in enumerate(cases)])
        for i, case in enumerate(cases):
            while True:
                if not case.dep_patterns:
                    break
                pat = case.dep_patterns.pop(0)
                matches = [
                    cases[k]
                    for (name, k) in case_map.items()
                    if i != k and fnmatch.fnmatchcase(name, pat)
                ]
                if not matches:
                    raise ValueError(
                        f"Dependency pattern {pat!r} of test case {case.name} not found"
                    )
                for match in matches:
                    assert isinstance(match, TestCase)
                    case.add_dependency(match)
        tty.verbose("Done resolving dependencies across test suite")

    def check_for_skipped_dependencies(self, cases: list[TestCase]) -> None:
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
