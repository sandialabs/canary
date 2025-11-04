# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import hashlib
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator

from . import config
from .error import StopExecution
from .error import notests_exit_status
from .finder import Finder
from .finder import generate_test_cases
from .generator import AbstractTestGenerator
from .testcase import TestCase
from .testcase import TestMultiCase
from .testcase import from_state as testcase_from_state
from .third_party.color import clen
from .third_party.lock import Lock
from .third_party.lock import LockError
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.graph import find_reachable_nodes
from .util.graph import static_order

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class CaseSelection:
    cases: list[TestCase]
    filters: dict[str, Any]
    tag: str | None = None
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
        self._created_on = timeformat(datetime.datetime.now())

        if self.tag is None:
            self.tag = self._created_on

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def created_on(self) -> str:
        return self._created_on


class Session:
    def __init__(self, root: Path, selection: CaseSelection) -> None:
        ts = timeformat(datetime.datetime.now())
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
            "working_directory": None,
            "execution_directory": None,
            "returncode": self.returncode,
            "status": "pending",
            "filters": selection.filters,
            "selection": selection.tag,
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
        data["started_on"] = timeformat(datetime.datetime.now())
        (self.path / "session.json").write_text(json.dumps(data, indent=2))
        return

    def exit(self) -> None:
        data = json.loads((self.path / "session.json").read_text())
        data["finished_on"] = timeformat(datetime.datetime.now())
        data["status"] = "complete"
        data["returncode"] = self.returncode
        (self.path / "session.json").write_text(json.dumps(data, indent=2))
        results: dict[str, Any] = {}
        for case in self.cases:
            case.refresh()
            results[case.id] = {
                "name": case.display_name,
                "returncode": case.returncode,
                "duration": case.duration,
                "started_on": timeformat(case.start),
                "finished_on": timeformat(case.stop),
                "working_directory": case.working_directory,
                "execution_directory": case.execution_directory,
                "status": {"value": case.status.value, "details": case.status.details},
            }
        (self.path / "results.json").write_text(json.dumps(results, indent=2))


class Repo:
    version_info = (1, 0, 0)

    def __init__(self, root: str | Path = Path.cwd() / ".canary") -> None:
        self.root = Path(root)
        self.objects_dir = self.root / "objects"
        self.cases_dir = self.objects_dir / "cases"
        self.generators_dir = self.objects_dir / "generators"
        self.refs_dir = self.root / "refs"
        self.sessions_dir = self.root / "sessions"
        self.cache_dir = self.root / "cache"
        self.tags_dir = self.root / "tags"
        self.head = self.root / "HEAD"
        self.lockfile = self.root / "lock"
        self.init()

    def init(self) -> None:
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.generators_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tags_dir.mkdir(parents=True, exist_ok=True)
        self.refs_dir.mkdir(parents=True, exist_ok=True)
        latest = self.sessions_dir / "results.json"
        if not latest.exists():
            latest.write_text(json.dumps({"cases": {}}))
        version = self.root / "VERSION"
        if not version.exists():
            ver = ".".join(str(_) for _ in self.version_info)
            version.write_text(f"{ver}")

    @classmethod
    def create(cls, path: Path, force: bool = False) -> "Repo":
        path = Path(path).absolute()
        d = path
        while True:
            if (d / ".canary").exists():
                if d == path and force:
                    shutil.rmtree(str(path / ".canary"))
                    break
                else:
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
                raise NotARepoError(
                    "not a Canary session (or any of the parent directories): .canary"
                )
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

            file = self.sessions_dir / "results.json"
            repo_results = json.loads(file.read_text())
            session_results = json.loads((session.path / "results.json").read_text())
            for id, entry in session_results.items():
                entry["session"] = str(session.path.name)
                repo_results["cases"][id] = entry
            file.write_text(json.dumps(repo_results, indent=2))

            # Write meta data file refs/latest -> ../sessions/{session.path}
            file = self.refs_dir / "latest"
            file.unlink(missing_ok=True)
            link = os.path.relpath(str(session.path), str(file.parent))
            file.write_text(str(link))

            # Write meta data file HEAD -> ./sessions/{session.path}
            self.head.unlink(missing_ok=True)
            link = os.path.relpath(str(file), str(self.head.parent))
            self.head.write_text(str(link))

            # Link LatestResults -> .canary/sessions/{session.work_dir}
            file = self.root.parent / "TestResults"
            if file.exists():
                if not file.is_symlink():
                    raise ValueError("The directory TestResults is not a symbolic link")
            file.unlink(missing_ok=True)
            link = os.path.relpath(str(session.work_dir), str(file.parent))
            file.symlink_to(link)

    def is_tag(self, name: str) -> bool:
        if name == "default":
            return True
        return (self.tags_dir / name).exists()

    def info(self) -> dict[str, Any]:
        import canary

        latest_session: str | None = None
        if (self.refs_dir / "latest").exists():
            link = (self.refs_dir / "latest").read_text().strip()
            path = self.refs_dir / link
            latest_session = path.stem
        info = {
            "root": str(self.root),
            "generator_count": len(list(self.generators_dir.rglob("*.json"))),
            "session_count": len([p for p in self.sessions_dir.glob("*") if p.is_dir()]),
            "latest_session": latest_session,
            "tags": sorted(p.stem for p in self.tags_dir.glob("*")),
            "version": canary.version,
            "repo_version": (self.root / "VERSION").read_text().strip(),
        }
        return info

    def add_generator(self, generator: AbstractTestGenerator, _warned: list[int] = [0]) -> int:
        file = self.generators_dir / generator.id[:2] / f"{generator.id[2:]}.json"
        if file.exists():
            logger.debug(f"Test case generator already in repo ({generator})")
            return 0

        file.parent.mkdir(parents=True, exist_ok=True)
        with self.write_lock(file):
            with open(file, "w") as fh:
                json.dump(generator.getstate(), fh, indent=2)

        # Invalidate caches
        for file in self.cache_dir.glob("*"):
            if not _warned[0]:
                logger.info("Invalidating previously locked test case cache")
                _warned[0] = 1
            cache = json.loads(file.read_text())
            cache["cases"] = None
            file.write_text(json.dumps(cache))

        return 1

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
        n: int = 0
        for generator in generators:
            n += self.add_generator(generator)
        logger.info(f"@*{{Added}} {n} new test case generators to {self.root}")
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

    def update_testcases(self, cases: list[TestCase]) -> None:
        """Update cases in ``cases`` with their latest results"""
        file = self.sessions_dir / "results.json"
        results = json.loads(file.read_text())
        for case in cases:
            if latest := results["cases"].get(case.id):
                if session := latest["session"]:
                    attrs = {
                        "session": str(self.sessions_dir / session / "work"),
                        "start": parsetime(latest["started_on"]),
                        "stop": parsetime(latest["finished_on"]),
                        "status": latest["status"],
                    }
                    case.update(**attrs)

    def select_testcases_by_spec(self, specs: list[str], tag: str | None = None) -> CaseSelection:
        ids: list[str] = []
        for spec in specs:
            if spec.startswith("/"):
                spec = spec[1:]
            for f in self.cases_dir.rglob(f"{spec[:2]}/{spec[2:]}*/{TestCase._lockfile}"):
                id = f"{f.parent.parent.stem}{f.parent.stem}"
                ids.append(id)
                break
            else:
                raise ValueError(f"{spec}: case not found")
        cases = self.load_testcases(ids=ids)
        for case in cases:
            case.mark_as_ready()
        selection = CaseSelection(
            cases=cases,
            filters={
                "case_specs": specs,
                "keyword_exprs": None,
                "parameter_expr": None,
                "owners": None,
                "on_options": None,
                "regex": None,
            },
            tag=tag,
        )
        self.cache_selection(selection)
        return selection

    def stage(
        self,
        tag: str | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        on_options: list[str] | None = None,
        regex: str | None = None,
        **kwargs: Any,
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
        config.pluginmanager.hook.canary_testsuite_mask(
            cases=cases,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            case_specs=None,
            start=None,
            ignore_dependencies=False,
        )
        for case in cases:
            self.add_testcase(case)

        default = all([not bool(_) for _ in (keyword_exprs, parameter_expr, owners, regex)])
        if tag is None and default:
            tag = "default"
        selected = [case for case in cases if not case.mask]
        n = len(selected)
        if not selected:
            logger.warning("Empty test case selection")
        selection = CaseSelection(
            cases=selected,
            filters={
                "keyword_exprs": keyword_exprs,
                "parameter_expr": parameter_expr,
                "owners": owners,
                "on_options": on_options,
                "regex": regex,
            },
            tag=tag,
        )
        self.cache_selection(selection)
        logger.info(f"@*{{Selected}} {n} test cases based on filtering criteria")
        return selection

    def cache_selection(self, selection: CaseSelection) -> None:
        id = selection.sha256[:10]
        cache_file = self.cache_dir / id
        cache = {
            "sha256": selection.sha256,
            "created_on": selection.created_on,
            "filters": selection.filters,
            "cases": [case.id for case in selection.cases],
            "tag": selection.tag,
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache))

        tag = selection.tag
        tag_file = self.tags_dir / tag
        tag_file.parent.mkdir(parents=True, exist_ok=True)
        link = os.path.relpath(str(cache_file), str(tag_file.parent))
        tag_file.write_text(str(link))

    def get_selection(self, tag: str | None = None):
        selection: CaseSelection
        # Use the last run case selection, if available
        if tag is None:
            if (self.refs_dir / "latest").exists():
                if (self.refs_dir / "latest").exists():
                    link = (self.refs_dir / "latest").read_text().strip()
                    file = self.refs_dir / link / "session.json"
                    latest = json.loads(file.read_text())
                    tag = latest["selection"].strip()
            else:
                tag = "default"
        file = self.tags_dir / tag
        if tag == "default" and not file.exists():
            logger.info("Creating default case selection")
            selection = self.stage(tag=tag)
            return selection
        relpath = file.read_text().strip()
        cache_file = self.tags_dir / relpath
        cache = json.loads(cache_file.read_text())
        if ids := cache.get("cases"):
            cases: list[TestCase] = self.load_testcases(ids=ids)
            selection = CaseSelection(cases=cases, filters=cache["filters"], tag=tag)
            selection._sha256 = cache["sha256"]
            selection._created_on = cache["created_on"]
            return selection

        # Cache was invalidated at some point
        selection = self.stage(tag=tag, **cache["filters"])
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

        file = self.sessions_dir / "results.json"
        results = json.loads(file.read_text())
        if case.id not in results["cases"]:
            results["cases"][case.id] = {
                "name": case.display_name,
                "session": None,
                "returncode": "NA",
                "duration": -1,
                "started_on": "NA",
                "finished_on": "NA",
                "status": {"value": case.status.value, "details": case.status.details},
            }
        file.write_text(json.dumps(results))

    def status(self) -> list[list[str]]:
        file = self.sessions_dir / "results.json"
        results = json.loads(file.read_text())
        table: list[list[str]] = []
        header = ["ID", "Name", "Session", "Exit Code", "Duration", "Status", "Details"]
        widths: list[int] = [len(_) for _ in header]
        def dformat(arg) -> str:
            return "NA" if arg < 0 else f"{arg:.02f}"
        for id, entry in results["cases"].items():
            # status = Status(entry["status"]["value"], entry["status"]["details"])
            row = [
                id[:7],
                entry["name"],
                entry["session"],
                entry["returncode"],
                dformat(entry["duration"]),
                entry["status"]["value"],
                entry["status"]["details"] or "",
            ]
            table.append(row)
            for i, x in enumerate(row):
                widths[i] = max(widths[i], clen(str(x)))
        table = sorted(table, key=lambda x: (status_value_sort_key(x[5]), x[1]))
        hlines = ["=" * width for width in widths]
        table.insert(0, hlines)
        table.insert(0, header)
        return table

    def gc(self) -> None:
        """Garbage collect"""
        removed: int = 0
        logger.info(f"Garbage collecting {self.root}")
        logger.warning("Garbage collection does not consider test case dependency graphs")
        for dir in self.sessions_dir.iterdir():
            if not dir.is_dir():
                continue
            file = dir / "results.json"
            results = json.loads(file.read_text())
            for data in results.values():
                if data["status"]["value"] == "success":
                    path = Path(data["working_directory"])
                    if path.exists():
                        logger.info(f"Removing working directory for {dir.stem}::{data['name']}")
                        force_remove(data["working_directory"])
                        removed += 1
        logger.info(f"Removed working directories for {removed} test cases")

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


def status_value_sort_key(name: str) -> int:
    map = {
        "invalid": 0,
        "created": 0,
        "retry": 0,
        "pending": 0,
        "ready": 0,
        "running": 0,
        "success": 10,
        "xfail": 11,
        "xdiff": 12,
        "cancelled": 19,
        "skipped": 20,
        "not_run": 21,
        "diffed": 22,
        "failed": 23,
        "timeout": 24,
        "unknown": 25,
    }
    return map[name]


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


def timeformat(dt: float | datetime.datetime) -> str:
    if isinstance(dt, (float, int)):
        dt = datetime.datetime.fromtimestamp(dt)
    return dt.strftime("%Y-%m-%dT%H-%M-%S.%f")


def parsetime(string: str) -> float:
    dt = datetime.datetime.strptime(string, "%Y-%m-%dT%H-%M-%S.%f")
    return dt.timestamp()


class NotARepoError(Exception):
    pass
