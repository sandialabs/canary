# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import datetime
from graphlib import TopologicalSorter
import os
from .util.graph import reachable_nodes
import pickle
import time
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from . import config
from .error import StopExecution
from .error import notests_exit_status
from .util import json_helper as json
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import select_sygil
from .util import logging
from .util.filesystem import working_dir
from .util.filesystem import write_directory_tag
from .util.graph import static_order
from .util.returncode import compute_returncode

if TYPE_CHECKING:
    from .workspace import SpecSelection

logger = logging.get_logger(__name__)
session_tag = "SESSION.TAG"


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
            space = ExecutionSpace(root=self.work_dir, path=spec.fullname, session=self.name)
            case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
            lookup[spec.id] = case
            self._cases.append(case)

        self.populate_worktree()

        # Dump a snapshot of the configuration used to create this session
        file = self.root / "config"
        with open(file, "w") as fh:
            config.dump_snapshot(fh)
        return self

    @property
    def selection(self) -> "SpecSelection":
        if self._selection is None:
            with open(self.select_file, "rb") as fh:
                self._selection = pickle.load(fh)
        assert self._selection is not None
        return self._selection

    @classmethod
    def load(cls, root: Path) -> "Session":
        if not (root / session_tag).exists():
            raise NotASessionError(root)
        self: Session = object.__new__(cls)
        self.initialize_properties(anchor=root.parent, name=root.name)
        # Load the configuration used to create this session
        file = self.root / "config"
        with open(file) as fh:
            config.load_snapshot(fh)
        return self

    @property
    def cases(self) -> list[TestCase]:
        if not self._cases:
            self._cases.extend(self.load_testcases())
        return self._cases

    def populate_worktree(self) -> None:
        for case in self.cases:
            path = Path(case.workspace.dir)
            path.mkdir(parents=True)
            case.save()

    def resolve_root_ids(self, roots: list[str]) -> None:
        """Expand roots to full IDs.  roots is a spec ID, or partial ID, and can be preceded by /"""
        ids: set[str] = {spec.id for spec in self.selection.specs}
        def find(root: str) -> str:
            if root in ids:
                return root
            for id in ids:
                if id.startswith(root):
                    return id
                elif root.startswith(select_sygil) and id.startswith(root[1:]):
                    return id
            raise SpecNotFoundError(root)
        for i, root in enumerate(roots):
            roots[i] = find(root)

    def load_testcases(self, roots: list[str] | None = None) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed."""
        specs = self.selection.specs
        graph = {spec.id: [d.id for d in spec.dependencies] for spec in specs}
        if roots:
            self.resolve_root_ids(roots)
            reachable = reachable_nodes(graph, roots)
            graph = {id: graph[id] for id in reachable}
        map: dict[str, TestSpec] = {spec.id: spec for spec in specs if spec.id in graph}
        lookup: dict[str, TestCase] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            spec = map[id]
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            space = ExecutionSpace(root=self.work_dir, path=spec.fullname, session=self.name)
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
        if roots:
            return [case for case in lookup.values() if case.id in roots]
        return list(lookup.values())

    def get_ready(self, roots: list[str] | None) -> list[TestCase]:
        if not roots:
            return self.cases
        self.resolve_root_ids(roots)
        return [case for case in self.cases if case.id in roots]

    def run(self, roots: list[str] | None = None) -> dict[str, Any]:
        # Since test cases run in subprocesses, we archive the config to the environment.  The
        # config object in the subprocess will read in the archive and use it to re-establish the
        # correct config
        config.archive(os.environ)
        cases = self.get_ready(roots=roots)
        if not cases:
            raise StopExecution("No tests to run", notests_exit_status)
        logger.info(f"@*{{Starting}} session {self.name}")
        start = time.monotonic()
        returncode: int = -1
        try:
            with working_dir(str(self.work_dir)):
                config.pluginmanager.hook.canary_runtests(cases=cases)
        finally:
            returncode = compute_returncode(cases)
            stop = time.monotonic()
            duration = stop - start
            logger.info(f"Finished session in {duration:.2f} s. with returncode {returncode}")
            return {"returncode": returncode, "cases": cases}

    def enter(self) -> None: ...

    def exit(self) -> None: ...


class NotASessionError(Exception):
    pass


class SessionExistsError(Exception):
    pass


class SpecNotFoundError(Exception):
    pass
