# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import os
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING

from . import config
from .error import StopExecution
from .error import notests_exit_status
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
        self.specs_file: Path
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
        self.specs_file = self.root / "specs.json"
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

        with open(self.specs_file, "w") as fh:
            data: list[dict] = []
            for spec in static_order(self.specs):
                data.append(spec.asdict())
            json.dump(data, fh, indent=2)
        write_directory_tag(self.root / session_tag)

        self._cases.clear()
        lookup: dict[str, TestCase] = {}
        for spec in static_order(self.specs):
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            space = ExecutionSpace(root=self.work_dir, path=Path(spec.execpath), session=self.name)
            case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
            lookup[spec.id] = case
            self._cases.append(case)

        # Dump a snapshot of the configuration used to create this session
        file = self.root / "config"
        with open(file, "w") as fh:
            config.dump(fh)

        return self

    @property
    def specs(self) -> list["TestSpec"]:
        from .testspec import TestSpec

        if not self._specs:
            lookup: dict[str, TestSpec] = {}
            with open(self.specs_file, "r") as fh:
                data = json.load(fh)
                for d in data:
                    spec = TestSpec.from_dict(d, lookup)
                    lookup[spec.id] = spec
                    self._specs.append(spec)
        return self._specs

    @classmethod
    def load(cls, root: Path) -> "Session":
        if not (root / session_tag).exists():
            raise NotASessionError(root)
        self: Session = object.__new__(cls)
        self.initialize_properties(anchor=root.parent, name=root.name)
        return self

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

    def load_testcases(self) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed."""
        specs = self.specs
        graph = {spec.id: [d.id for d in spec.dependencies] for spec in specs}
        map: dict[str, "TestSpec"] = {spec.id: spec for spec in specs if spec.id in graph}
        lookup: dict[str, "TestCase"] = {}
        ts = TopologicalSorter(graph)
        pm = logger.progress_monitor("@*{Loading} test cases into session")
        for id in ts.static_order():
            spec = map[id]
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            space = ExecutionSpace(root=self.work_dir, path=Path(spec.execpath), session=self.name)
            case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
            f = case.workspace.dir / "testcase.lock"
            if f.exists():
                data = json.loads(f.read_text())
                case.status.set(
                    data["status"]["name"],
                    message=data["status"]["message"],
                    code=data["status"]["code"],
                )
                case.timekeeper.started_on = data["timekeeper"]["started_on"]
                case.timekeeper.finished_on = data["timekeeper"]["finished_on"]
                case.timekeeper.duration = data["timekeeper"]["duration"]
            lookup[case.spec.id] = case
        cases = list(lookup.values())
        pm.done()
        return cases

    def get_ready(self, ids: list[str] | None) -> list[TestCase]:
        if not ids:
            return self.cases
        self.resolve_root_ids(ids)
        return [case for case in self.cases if case.id in ids]

    def run(self, ids: list[str] | None = None) -> SessionResults:
        cases = self.get_ready(ids=ids)
        if not cases:
            raise StopExecution("No tests to run", notests_exit_status)
        starting_dir = os.getcwd()
        started_on = datetime.datetime.now()
        try:
            for case in cases:
                case.status.set("PENDING")
            os.chdir(str(self.work_dir))
            runner = Runner(cases=cases, session=self)
            canary_runtests(runner=runner)
        finally:
            finished_on = datetime.datetime.now()
            os.chdir(starting_dir)
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
