# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import os
import sqlite3
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from . import config
from .error import StopExecution
from .error import notests_exit_status
from .filter import ExecutionContextFilter
from .runtest import Runner
from .runtest import canary_runtests
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import select_sygil
from .util import json_helper as json
from .util import logging
from .util.filesystem import write_directory_tag
from .util.graph import static_order

if TYPE_CHECKING:
    from .testspec import TestSpec

logger = logging.get_logger(__name__)
session_tag = "SESSION.TAG"


@dataclasses.dataclass
class SessionResults:
    session: str
    cases: list[TestCase]
    returncode: int
    started_on: datetime.datetime
    finished_on: datetime.datetime
    prefix: Path


class Session:
    def __init__(self) -> None:
        # Even through this function is not meant to be called, we declare types so that code
        # editors know what to work with.
        self.name: str
        self.root: Path
        self.work_dir: Path
        self.db: sqlite3.Connection
        self._cases: list[TestCase]
        self._specs: list["TestSpec"]
        raise RuntimeError("Use Session factory methods create and load")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def initialize_properties(self, *, anchor: Path, name: str) -> None:
        self.name = name
        self.root = anchor / self.name
        self._cases = []
        self.work_dir = self.root / "work"
        self._specs = []

    @staticmethod
    def is_session(path: Path) -> bool:
        return (path / session_tag).exists()

    @classmethod
    def create(cls, anchor: Path, specs: list["TestSpec"]) -> "Session":
        if not specs:
            raise StopExecution("Empty test session", notests_exit_status)
        self: Session = object.__new__(cls)
        ts = datetime.datetime.now().isoformat(timespec="microseconds")
        self.initialize_properties(anchor=anchor, name=ts.replace(":", "-"))
        if self.root.exists() or (self.root / session_tag).exists():
            raise SessionExistsError(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._specs = specs
        write_directory_tag(self.root / session_tag)
        self._cases.clear()
        lookup: dict[str, TestCase] = {}
        for spec in static_order(self.specs):
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            space = ExecutionSpace(root=self.work_dir, path=Path(spec.execpath), session=self.name)
            case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
            lookup[spec.id] = case
            self._cases.append(case)

        filter = ExecutionContextFilter(self._cases)
        filter.run()

        dbfile = self.root / "session.sqlite3"
        self.db = sqlite3.connect(dbfile, timeout=30.0, isolation_level=None)
        cursor = self.db.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_key=ON;")
        cursor.execute("CREATE TABLE IF NOT EXISTS specs (id TEXT PRIMARY KEY, data TEXT)")
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS results (
                id TEXT PRIMARY KEY, status TEXT, timekeeper TEXT, workspace TEXT
            )"""
        )
        self.db.commit()

        self.save_specs(self._specs)
        self.save_results(self._cases)
        self.save_config()

        return self

    @classmethod
    def load(cls, root: Path) -> "Session":
        if not (root / session_tag).exists():
            raise NotASessionError(root)
        self: Session = object.__new__(cls)
        self.initialize_properties(anchor=root.parent, name=root.name)
        dbfile = self.root / "session.sqlite3"
        self.db = sqlite3.connect(dbfile, timeout=30.0, isolation_level=None)
        cursor = self.db.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_key=ON;")
        return self

    def save_config(self) -> None:
        # Dump a snapshot of the configuration used to create this session
        file = self.root / "config"
        with open(file, "w") as fh:
            config.dump(fh)

    def load_specs(self) -> list["TestSpec"]:
        from .testspec import TestSpec

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM specs")
        rows = cursor.fetchall()
        data = {id: json.loads(data) for id, data in rows}
        graph = {id: [_["id"] for _ in s["dependencies"]] for id, s in data.items()}
        lookup: dict[str, TestSpec] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            spec = TestSpec.from_dict(data[id], lookup)
            lookup[id] = spec
        return list(lookup.values())

    def save_specs(self, specs: list["TestSpec"]) -> None:
        cursor = self.db.cursor()
        cursor.executemany(
            """
            INSERT INTO specs (id, data)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data
            """,
            [(spec.id, json.dumps_min(spec.asdict())) for spec in specs],
        )
        self.db.commit()

    def load_testcases(self) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed."""
        specs = self.specs
        graph = {spec.id: [d.id for d in spec.dependencies] for spec in specs}
        map: dict[str, "TestSpec"] = {spec.id: spec for spec in specs if spec.id in graph}
        lookup: dict[str, "TestCase"] = {}
        ts = TopologicalSorter(graph)
        pm = logger.progress_monitor("@*{Loading} test cases")
        results = self.get_results()
        try:
            for id in ts.static_order():
                spec = map[id]
                dependencies = [lookup[dep.id] for dep in spec.dependencies]
                result = results[id]
                space = ExecutionSpace(
                    root=Path(result["workspace"]["root"]),
                    path=Path(result["workspace"]["path"]),
                    session=result["workspace"]["session"],
                )
                case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
                case.status.set(
                    result["status"]["name"],
                    reason=result["status"]["reason"],
                    code=result["status"]["code"],
                )
                case.timekeeper.started_on = result["timekeeper"]["started_on"]
                case.timekeeper.finished_on = result["timekeeper"]["finished_on"]
                case.timekeeper.duration = result["timekeeper"]["duration"]
                lookup[case.spec.id] = case
            cases = list(lookup.values())
        except:
            logger.exception("uncaught exception")
            raise
        pm.done()
        return cases

    def save_results(self, cases: list["TestCase"]) -> None:
        rows = []
        for case in cases:
            rows.append(
                (
                    case.id,
                    json.dumps_min(case.status.asdict()),
                    json.dumps_min(case.timekeeper.asdict()),
                    json.dumps_min(case.workspace.asdict()),
                )
            )
        cursor = self.db.cursor()
        cursor.executemany(
            """
            INSERT INTO results (id, status, timekeeper, workspace)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              status=excluded.status,
              timekeeper=excluded.timekeeper,
              workspace=excluded.workspace
            """,
            rows,
        )
        self.db.commit()

    def get_results(self) -> dict[str, dict[str, Any]]:
        cursor = self.db.cursor()
        cursor.execute("SELECT id, status, timekeeper, workspace  FROM results")
        rows = cursor.fetchall()
        return {
            id: {
                "status": json.loads(status),
                "timekeeper": json.loads(timekeeper),
                "workspace": json.loads(workspace),
            }
            for id, status, timekeeper, workspace in rows
        }

    @property
    def specs(self) -> list["TestSpec"]:
        if not self._specs:
            self._specs.extend(self.load_specs())
        return self._specs

    @property
    def cases(self) -> list[TestCase]:
        if not self._cases:
            self._cases.extend(self.load_testcases())
        return self._cases

    def resolve_root_ids(self, ids: list[str]) -> None:
        """Expand ids to full IDs.  ids is a spec ID, or partial ID, and can be preceded by /"""
        nodes: set[str] = {spec.id for spec in self.specs}

        def find(id: str) -> str:
            if id in nodes:
                return id
            for node in nodes:
                if node.startswith(id):
                    return node
                elif id.startswith(select_sygil) and node.startswith(id[1:]):
                    return node
            raise SpecNotFoundError(id)

        for i, id in enumerate(ids):
            ids[i] = find(id)

    def get_ready(self, ids: list[str] | None) -> list[TestCase]:
        cases: list[TestCase]
        if not ids:
            cases = self.cases
        else:
            self.resolve_root_ids(ids)
            cases = []
            for case in self.cases:
                if case.id in ids:
                    # case was explicitly requested, set its status to pending
                    case.status.set("PENDING")
                    cases.append(case)
        return [case for case in cases if case.status.category in ("READY", "PENDING")]

    def run(self, ids: list[str] | None = None) -> SessionResults:
        cases = self.get_ready(ids=ids)
        if not cases:
            raise StopExecution("No tests to run", notests_exit_status)
        starting_dir = os.getcwd()
        started_on = datetime.datetime.now()
        runner = Runner(cases=cases, session=self)
        try:
            for case in cases:
                case.status.set("PENDING")
            os.chdir(str(self.work_dir))
            canary_runtests(runner=runner)
        except Exception:
            logger.exception("session run failed")
        finally:
            finished_on = datetime.datetime.now()
            os.chdir(starting_dir)
            self.save_results(cases)
            return SessionResults(
                session=self.name,
                cases=cases,
                returncode=runner.returncode,
                started_on=started_on,
                finished_on=finished_on,
                prefix=self.root,
            )

    def enter(self) -> None: ...

    def exit(self) -> None: ...


class NotASessionError(Exception):
    pass


class SessionExistsError(Exception):
    pass


class SpecNotFoundError(Exception):
    pass
