# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import os
import pickle  # nosec B403
import time
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING

from . import config
from .error import StopExecution
from .error import notests_exit_status
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import select_sygil
from .util import json_helper as json
from .util import logging
from .util.filesystem import write_directory_tag
from .util.graph import static_order
from .util.returncode import compute_returncode

if TYPE_CHECKING:
    from .testspec import TestSpec
    from .workspace import SpecSelection

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
        self.select_file: Path
        self._cases: list[TestCase]
        self._selection: "SpecSelection | None"
        raise RuntimeError("Use Session factory methods create and load")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def initialize_properties(self, *, anchor: Path, name: str) -> None:
        self.name = name
        self.root = anchor / self.name
        self._cases = []
        self.work_dir = self.root / "work"
        self.select_file = self.root / "selection"
        self._selection = None

    @staticmethod
    def is_session(path: Path) -> Path | None:
        return (path / session_tag).exists()

    @classmethod
    def create(cls, anchor: Path, selection: "SpecSelection") -> "Session":
        self: Session = object.__new__(cls)
        ts = datetime.datetime.now().isoformat(timespec="microseconds")
        self.initialize_properties(anchor=anchor, name=ts.replace(":", "-"))
        if self.root.exists() or (self.root / session_tag).exists():
            raise SessionExistsError(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        with open(self.select_file, "wb") as fh:
            pickle.dump(selection, fh)
        self._selection = selection
        write_directory_tag(self.root / session_tag)

        self._cases.clear()
        specs = self.selection.specs
        lookup: dict[str, TestCase] = {}
        for spec in static_order(specs):
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            space = ExecutionSpace(root=self.work_dir, path=spec.execpath, session=self.name)
            case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
            lookup[spec.id] = case
            config.pluginmanager.hook.canary_testcase_modify(case=case)
            if case.mask:
                raise ValueError(
                    f"{case}: mask changed unexpectedly.  "
                    f"Masks should be updated by canary_select_modifyitems"
                )
            self._cases.append(case)

        # Dump a snapshot of the configuration used to create this session
        file = self.root / "config"
        with open(file, "w") as fh:
            config.dump(fh)
        return self

    @property
    def selection(self) -> "SpecSelection":
        if self._selection is None:
            with open(self.select_file, "rb") as fh:
                self._selection = pickle.load(fh)  # nosec B301
        assert self._selection is not None
        return self._selection

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
        nodes: set[str] = {spec.id for spec in self.selection.specs}

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
        specs = self.selection.specs
        graph = {spec.id: [d.id for d in spec.dependencies] for spec in specs}
        map: dict[str, "TestSpec"] = {spec.id: spec for spec in specs if spec.id in graph}
        lookup: dict[str, "TestCase"] = {}
        ts = TopologicalSorter(graph)
        pm = logger.progress_monitor("@*{Loading} test cases into session")
        for id in ts.static_order():
            spec = map[id]
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            space = ExecutionSpace(root=self.work_dir, path=spec.execpath, session=self.name)
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
            config.pluginmanager.hook.canary_testcase_modify(case=case)
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
        logger.info(f"@*{{Starting}} session {self.name}")
        start = time.monotonic()
        returncode: int = -1
        try:
            started_on = datetime.datetime.now()
            starting_dir = os.getcwd()
            changed = False
            for case in cases:
                case.status.set("PENDING")
            final = [case for case in cases if not case.mask]
            os.chdir(str(self.work_dir))
            config.pluginmanager.hook.canary_runtests(cases=final)
        except TimeoutError:
            logger.error(f"Session timed out after {(time.monotonic() - start):.2f} s.")
        except Exception:
            logger.exception("Unhandled exception in runtests")
            raise
        finally:
            finished_on = datetime.datetime.now()
            os.chdir(starting_dir)
            returncode = compute_returncode(cases)
            logger.info(
                f"@*{{Finished}} session in {(time.monotonic() - start):.2f} s. "
                f"with returncode {returncode}"
            )
            return SessionResults(
                session=self.name,
                cases=cases,
                returncode=returncode,
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
