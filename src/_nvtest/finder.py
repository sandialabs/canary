import fnmatch
import os
from itertools import repeat
from typing import Any
from typing import Optional

from . import config
from . import plugin
from .test.case import TestCase
from .test.file import AbstractTestFile
from .util import filesystem as fs
from .util import logging
from .util import parallel
from .util.resource import ResourceInfo


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

    def discover(self) -> list[AbstractTestFile]:
        tree: dict[str, set[AbstractTestFile]] = {}
        if not self._ready:
            raise ValueError("Cannot call populate() before calling prepare()")
        for root, paths in self.roots.items():
            logging.debug(f"Searching {root} for test files")
            if os.path.isfile(root):
                f = AbstractTestFile.factory(root)
                root = f.root
                testfiles = tree.setdefault(root, set())
                testfiles.add(f)
            elif paths is not None:
                testfiles = tree.setdefault(root, set())
                for path in paths:
                    p = os.path.join(root, path)
                    if os.path.isfile(p):
                        testfiles.add(AbstractTestFile.factory(root, path))
                    elif os.path.isdir(p):
                        testfiles.update(self.rfind(root, subdir=path))
                    else:
                        raise FileNotFoundError(path)
            else:
                testfiles = tree.setdefault(root, set())
                testfiles.update(self.rfind(root))
            logging.debug(f"Found {len(testfiles)} test files in {root}")
        n = sum([len(_) for _ in tree.values()])
        nr = len(tree)
        logging.debug(f"Found {n} test files in {nr} search roots")
        files: list[AbstractTestFile] = [file for files in tree.values() for file in files]
        return files

    def rfind(self, root: str, subdir: Optional[str] = None) -> list[AbstractTestFile]:
        def skip_dir(dirname):
            if os.path.basename(dirname) in self.skip_dirs:
                return True
            if fs.is_hidden(dirname):
                return True
            if os.path.exists(os.path.join(dirname, ".nvtest")):
                return True
            return False

        file_types = tuple(config.file_types)
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
        testfiles: list[AbstractTestFile] = parallel.starmap(AbstractTestFile.factory, paths)

        return testfiles

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
            if case.status != "created":
                continue
            for dep in case.dependencies:
                if id(dep) not in ids:
                    logging.error(f"ID of {dep!r} is not in test cases")
                    missing += 1
                if dep.status != "created":
                    case.status.set("masked", "deselected due to skipped dependency")
                    logging.warning(f"Dependency {dep!r} of {case!r} is marked to be skipped")
        if missing:
            raise ValueError("Missing dependencies")
        logging.debug("Done validating test cases")

    @staticmethod
    def freeze(
        files: list[AbstractTestFile],
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
            avail_cpus=resourceinfo["test:cpus"],
            avail_devices=resourceinfo["test:devices"],
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
        if any(case.status.value not in ("created", "masked") for case in cases):
            raise ValueError("One or more test cases is not in created state")

        for hook in plugin.plugins("test", "discovery"):
            for case in cases:
                hook(case)

        Finder.resolve_dependencies(cases)
        Finder.check_for_skipped_dependencies(cases)

        logging.debug("Done creating test cases")
        return cases


def is_test_file(file: str) -> bool:
    file_types = tuple(config.file_types)
    return file.endswith(file_types)


def freeze_abstract_file(file: AbstractTestFile, kwds: dict) -> list[TestCase]:
    concrete_test_cases = file.freeze(**kwds)
    return concrete_test_cases


class FinderError(Exception):
    pass
