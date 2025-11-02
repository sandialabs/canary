# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator
from typing import IO

from . import config
from .error import StopExecution
from .error import notests_exit_status
from .finder import generate_test_cases
from .finder import Finder
from .generator import AbstractTestGenerator
from .mask import mask_testcases
from .testcase import TestCase
from .testcase import TestMultiCase
from .testcase import from_state as testcase_from_state
from .third_party.lock import Lock
from .third_party.lock import LockError
from .util import logging
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.graph import find_reachable_nodes
from .util.graph import static_order

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class CaseSelection:
    cases: list[TestCase]
    filters: dict[str, Any]
    _sha256: str = dataclasses.field(init=False)
    _created_on: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        cases = sorted([case.id for case in self.cases])
        filters: dict[str, Any] = {}
        for name, value in filters.items():
            if isinstance(value, list):
                filters[name] = sorted(value)
            else:
                filters[name] = value
        text = json.dumps({"cases": cases, "filters": filters})
        self._sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._created_on = datetime.datetime.now().isoformat()

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def created_on(self) -> str:
        return self._created_on

    def is_default_selection(self) -> bool:
        return all([value is None for value in self.filters.values()])


class Session:
    def __init__(self, root: Path, selection: CaseSelection) -> None:
        ts = datetime.datetime.now().isoformat()
        self.path = root / ts
        self.cases = selection.cases
        self.path.mkdir(parents=True, exist_ok=True)
        self.work_dir = self.path / "work"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.returncode: int = -10
        for case in self.cases:
            case.session = str(self.work_dir)
        data = {
            "created_on": ts,
            "started_on": None,
            "finished_on": None,
            "returncode": self.returncode,
            "status": "not run",
            "filters": selection.filters,
        }
        (self.path / "session.json").write_text(json.dumps(data, indent=2))

    def get_ready(self) -> list[TestCase]:
        for case in static_order(self.cases):
            config.pluginmanager.hook.canary_testcase_modify(case=case)
        ready: list[TestCase] = []
        for case in self.cases:
            if not case.wont_run():
                case.mark_as_ready()
                ready.append(case)
        return ready

    def run_all(self) -> None:
        cases = self.get_ready()
        if not cases:
            raise StopExecution("No tests to run", notests_exit_status)
        start = time.monotonic()
        with working_dir(str(self.work_dir)):
            self.returncode = config.pluginmanager.hook.canary_runtests(cases=cases)
        stop = time.monotonic()
        duration = stop - start
        logger.info(f"Finished session in {duration:.2f} s.")

    def enter(self) -> None:
        data = json.loads((self.path / "session.json").read_text())
        data["started_on"] = datetime.datetime.now().isoformat()
        (self.path / "session.json").write_text(json.dumps(data, indent=2))
        return

    def exit(self) -> None:
        data = json.loads((self.path / "session.json").read_text())
        data["finished_on"] = datetime.datetime.now().isoformat()
        data["returncode"] = self.returncode
        (self.path / "session.json").write_text(json.dumps(data, indent=2))
        results: dict[str, Any] = {}
        for case in self.cases:
            results[case.id] = {
                "name": case.display_name,
                "started_on": datetime.datetime.fromtimestamp(case.start).isoformat(),
                "finished_on": datetime.datetime.fromtimestamp(case.stop).isoformat(),
                "status": {"value": case.status.value, "details": case.status.details}
            }
        (self.path / "results.json").write_text(json.dumps(results, indent=2))


class Repo:
    def __init__(self, root: str | Path = Path.cwd() / ".canary") -> None:
        self.root = Path(root)
        self.objects_dir = self.root / "objects"
        self.cases_dir = self.objects_dir / "cases"
        self.generators_dir = self.objects_dir / "generators"
        self.refs_dir = self.root / "refs"
        self.sessions_dir = self.root / "sessions"
        self.state_dir = self.root / "state"
        self.cache_dir = self.root / "cache"
        self.tags_dir = self.root / "tags"
        self.head = self.root / "HEAD"
        self.lockfile = self.root / "lock"
        self.init()

    def init(self) -> None:
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.generators_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tags_dir.mkdir(parents=True, exist_ok=True)
        self.refs_dir.mkdir(parents=True, exist_ok=True)
        latest = self.state_dir / "latest.json"
        if not latest.exists():
            latest.write_text(json.dumps({"cases": {}}))

    @classmethod
    def create(cls, path: Path) -> "Repo":
        path = Path(path).absolute()
        d = path
        while True:
            if (d / ".canary").exists():
                raise ValueError(f".canary already exists at {d}")
            if d.parent == d:
                break
            d = d.parent
        self = cls(path / ".canary")
        return self

    @classmethod
    def load(cls, start: Path | None = None) -> "Repo":
        start = start or Path.cwd()
        while True:
            if (start / ".canary").exists():
                break
            if start.parent == start:
                raise NotARepoError("not a Canary session (or any of the parent directories): .canary")
            start = start.parent
        self = cls(start / ".canary")
        return self

    @contextmanager
    def session(self, selection: CaseSelection) -> Generator[Session, None, None]:
        try:
            session = Session(self.sessions_dir, selection)
            session.enter()
            yield session
        finally:
            session.exit()
            file = self.state_dir / "latest.json"
            latest = json.loads(file.read_text())
            for case in session.cases:
                latest["cases"][case.id] = case.getstate(
                    "start", "stop", "returncode", "session", "status", "measurements", "name", "id"
                )
            file.write_text(json.dumps(latest, indent=2))

            file = self.refs_dir / "latest"
            file.unlink(missing_ok=True)
            file.symlink_to(session.work_dir)
            self.head.unlink(missing_ok=True)
            self.head.symlink_to(self.refs_dir / "latest")
            file = self.root.parent / "TestResults"
            file.unlink(missing_ok=True)
            file.symlink_to(self.refs_dir / "latest")

    def add_generator(self, generator: AbstractTestGenerator) -> None:
        file = self.generators_dir / generator.id[:2] / f"{generator.id[2:]}.json"
        if file.exists():
            logger.warning("Test case already added to repo")
            return

        file.parent.mkdir(parents=True, exist_ok=True)
        with self.write_lock(file):
            with open(file, "w") as fh:
                json.dump(generator.getstate(), fh, indent=2)

    def load_testcase_generators(self) -> list[AbstractTestGenerator]:
        """Load test case generators"""
        generators: list[AbstractTestGenerator] = []
        msg = "@*{Loading} test case generators"
        logger.log(logging.DEBUG, msg, extra={"end": "..."})
        start = time.monotonic()
        try:
            for file in self.generators_dir.rglob("*.json"):
                state = json.loads(file.read_text())
                generator = AbstractTestGenerator.from_state(state)
                generators.append(generator)
        except Exception:
            status = "failed"
            raise
        else:
            status = "done"
        finally:
            end = "... %s (%.2fs.)\n" % (status, time.monotonic() - start)
            extra = {"end": end, "rewind": True}
            logger.log(logging.DEBUG, msg, extra=extra)
        return generators

    def collect_testcase_generators(
        self, scan_paths: dict[str, list[str]], pedantic: bool = True
    ) -> list[AbstractTestGenerator]:
        finder = Finder()
        for root, paths in scan_paths.items():
            finder.add(root, *paths, tolerant=True)
        finder.prepare()
        generators = finder.discover(pedantic=pedantic)
        for generator in generators:
            self.add_generator(generator)
        logger.debug(f"Discovered {len(generators)} test files")
        return generators

    def load_testcases(self, ids: list[str] | None = None) -> list[TestCase]:
        """Load test cases previously dumped by ``dump_testcases``.  Dependency resolution is also
        performed
        """
        msg = "@*{Loading} test cases"
        start = time.monotonic()
        logger.log(logging.DEBUG, msg, extra={"end": "..."})
        cases: dict[str, TestCase | TestMultiCase] = {}
        try:
            file = self.cases_dir / "index.jsons"
            # index format: {ID: [DEPS_IDS]}
            index: dict[str, list[str]] = {}
            for line in file.read_text().splitlines():
                entry = json.loads(line)
                index.update(entry)
            ids_to_load: set[str] = set()
            if ids:
                # we must not only load the requested IDs, but also their dependencies
                for id in ids:
                    ids_to_load.update(find_reachable_nodes(index, id))
            ts: TopologicalSorter = TopologicalSorter()
            for id, deps in index.items():
                ts.add(id, *deps)
            for id in ts.static_order():
                if ids_to_load and id not in ids_to_load:
                    continue
                # see TestCase.lockfile for file pattern
                file = self.cases_dir / id[:2] / id[2:] / TestCase._lockfile
                with self.read_lock(file):
                    state = json.loads(file.read_text())
                for i, dep_state in enumerate(state["properties"]["dependencies"]):
                    # assign dependencies from existing dependencies
                    state["properties"]["dependencies"][i] = cases[dep_state["properties"]["id"]]
                cases[id] = testcase_from_state(state)
                assert id == cases[id].id
        except Exception:
            state = "failed"
            raise
        else:
            state = "done"
        finally:
            end = "... %s (%.2fs.)\n" % (state, time.monotonic() - start)
            extra = {"end": end, "rewind": True}
            logger.log(logging.DEBUG, msg, extra=extra)
        return list(cases.values())

    def get_testcases(
        self,
        generators: list[AbstractTestGenerator],
        on_options: list[str] | None = None,
        ) -> list[TestCase]:

        cases: list[TestCase] = []
        generators = self.load_testcase_generators()

        case_ids: set[str] = set()
        remaining = []
        for generator in generators:
            file = Path(self.generators_dir) / generator.id[:2] / f"{generator.id[2:]}.json"
            f = file.with_suffix(".cache")
            if f.exists():
                cache = json.loads(f.read_text())
                for entry in cache:
                    if entry["on_options"] == on_options:
                        case_ids.update(entry["cases"])
                        break
                else:
                    remaining.append(generator)

        if case_ids:
            cases = self.load_testcases(ids=case_ids)

        if remaining:
            cases = generate_test_cases(remaining, on_options=on_options)

        groups: dict[str, list[TestCase]] = {}
        map = {Path(generator.file).absolute(): generator.id for generator in generators}
        for case in cases:
            for f in map:
                if f.samefile(case.file):
                    groups.setdefault(f, []).append(case)
                    break
            else:
                raise ValueError(f"Could not find generator for {case}")
        for f, values in groups.items():
            id = map[f]
            file = Path(self.generators_dir) / id[:2] / f"{id[2:]}.cases.json"
            cache: list[dict] = []
            if file.exists():
                cache = json.loads(file.read_text())
            for entry in cache:
                if entry["on_options"] == on_options:
                    break
            else:
                cache.append({"on_options": on_options, "cases": [case.id for case in values]})
            file.write_text(json.dumps(cache, indent=2))
        for case in cases:
            file = self.cases_dir / case.id[:2] / f"{case.id[2:]}.json"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(case.getstate()))
        return cases

    def lock(
        self,
        tag: str | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        on_options: list[str] | None = None,
        start: str | None = None,
        regex: str | None = None,
    ) -> CaseSelection:
        """Generate (lock) test cases from generators

        Args:
          keyword_exprs: Used to filter tests by keyword.  E.g., if two test define the keywords
            ``baz`` and ``spam``, respectively and ``keyword_expr = 'baz or spam'`` both tests will
            be locked and marked as ready.  However, if a test defines only the keyword ``ham`` it
            will be marked as "skipped by keyword expression".
          parameter_expr: Used to filter tests by parameter.  E.g., if a test is parameterized by
            ``a`` with values ``1``, ``2``, and ``3`` and you want to only run the case for ``a=1``
            you can filter the other two cases with the parameter expression
            ``parameter_expr='a=1'``.  Any test case not having ``a=1`` will be marked as "skipped by
            parameter expression".
          on_options: Used to filter tests by option.  In the typical case, options are added to
            ``on_options`` by passing them on the command line, e.g., ``-o dbg`` would add ``dbg`` to
            ``on_options``.  Tests can define filtering criteria based on what options are on.
          owners: Used to filter tests by owner.

        Returns:
          A list of test cases

        """
        generators = self.load_testcase_generators()
        cases = generate_test_cases(generators, on_options=on_options)
        mask_testcases(
            cases,
            config,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            start=start,
            ignore_dependencies=False,
        )
        for case in cases:
            self.add_testcase(case)
        selection = CaseSelection(
            cases=[case for case in cases if not case.mask],
            filters={
                "keyword_exprs": keyword_exprs,
                "parameter_expr": parameter_expr,
                "owners": owners,
                "on_options": on_options,
                "regex": regex,
                "start": start,
            },
        )
        self.cache_selection(selection, tag=tag)
        return selection

    def cache_selection(self, selection: CaseSelection, tag: str | None = None) -> None:
        id = selection.sha256[:20]
        cache_file = self.cache_dir / id[:2] / id[2:]
        cache = {
            "sha256": selection.sha256,
            "created_on": selection.created_on,
            "filters": selection.filters,
            "cases": [case.id for case in selection.cases]
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache))

        if tag is None:
            if selection.is_default_selection():
                tag = "default"
            else:
                tag = selection.created_on
        tag_file = self.tags_dir / tag
        tag_file.parent.mkdir(parents=True, exist_ok=True)
        link = os.path.relpath(str(cache_file), str(tag_file.parent))
        tag_file.write_text(str(link))

    def get_selection(self, tag: str | None = None):
        selection: CaseSelection
        if tag is None:
            selection = self.lock()
        else:
            file = self.tags_dir / tag
            relpath = file.read_text().strip()
            cache_file = self.tags_dir / relpath
            cache = json.loads(cache_file.read_text())
            cases: list[TestCase] = self.load_testcases(ids=cache["cases"])
            selection = CaseSelection(filters=cache["filters"], cases=cases)
            selection._sha256 = cache["sha256"]
            selection._created_on = cache["created_on"]
        return selection

    def add_testcase(self, case: TestCase) -> None:
        file = self.cases_dir / case.id[:2] / case.id[2:] / "testcase.lock"
        if file.exists():
            return

        file.parent.mkdir(parents=True, exist_ok=True)
        with self.write_lock(file):
            with open(file, "w") as fh:
                json.dump(case.getstate(), fh, indent=2)

        file = self.cases_dir / "index.jsons"
        with self.read_lock(file):
            with file.open(mode="a") as fh:
                fh.write(json.dumps({case.id: [dep.id for dep in case.dependencies]}) + "\n")

    def report_status(self, file: IO[Any] | None = None) -> None:
        file = file or sys.stdout
        state_file = self.state_dir / "latest.json"
        state = json.loads(state_file.read_text())
        groups = {}
        for id, entry in state["cases"].items():
            groups.setdefault(entry["properties"]["status"]["value"], []).append(entry)
        table: list[list[str]] = []
        for status, entries in groups.items():
            for entry in entries:
                file.write(f"{status}: {entry['properties']['name']}\n")

    @contextmanager
    def read_lock(self, file: Path) -> Generator[Lock, None, None]:
        sha1 = hashlib.sha1(str(file).encode("utf-8")).digest()
        lock_id = prefix_bits(sha1, bit_length(sys.maxsize))
        lock = Lock(
            str(self.lockfile),
            start=lock_id,
            length=1,
            desc=str(file),
        )
        lock.acquire_read()
        try:
            yield lock
        except LockError:
            # This addresses the case where a nested lock attempt fails inside
            # of this context manager
            raise
        except (Exception, KeyboardInterrupt):
            lock.release_read()
            raise
        else:
            lock.release_read()

    @contextmanager
    def write_lock(self, file: Path) -> Generator[Lock, None, None]:
        sha1 = hashlib.sha1(str(file).encode("utf-8")).digest()
        lock_id = prefix_bits(sha1, bit_length(sys.maxsize))
        lock = Lock(
            str(self.lockfile),
            start=lock_id,
            length=1,
            desc=str(file),
        )
        lock.acquire_write()
        try:
            yield lock
        except LockError:
            # This addresses the case where a nested lock attempt fails inside
            # of this context manager
            raise
        except (Exception, KeyboardInterrupt):
            lock.release_write()
            raise
        else:
            lock.release_write()


def prefix_bits(byte_array: bytes, bits: int) -> int:
    """Return the first <bits> bits of a byte array as an integer."""
    b2i = lambda b: b  # In Python 3, indexing byte_array gives int
    result = 0
    n = 0
    for i, b in enumerate(byte_array):
        n += 8
        result = (result << 8) | b2i(b)
        if n >= bits:
            break
    result >>= n - bits
    return result


def bit_length(arg: int):
    """Number of bits required to represent an integer in binary."""
    s = bin(arg)
    s = s.lstrip("-0b")
    return len(s)


class NotARepoError(Exception):
    pass
