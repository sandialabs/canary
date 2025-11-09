# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import hashlib
import json
import os
import pickle
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator

from . import config
from . import testspec
from .error import StopExecution
from .error import notests_exit_status
from .generator import AbstractTestGenerator
from .plugins.types import ScanPath
from .testcase import TestCase
from .testcase import TestMultiCase
from .testcase import from_state as testcase_from_state
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.graph import find_reachable_nodes
from .util.graph import static_order

logger = logging.get_logger(__name__)

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
view_tag = "VIEW.TAG"
session_tag = "SESSION.TAG"


@dataclasses.dataclass
class SpecSelection:
    specs: list[testspec.TestSpec]
    tag: str | None
    _sha256: str = dataclasses.field(init=False)
    _created_on: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        specs = sorted([spec.id for spec in self.specs])
        text = json.dumps({"tag": self.tag, "specs": specs})
        self._sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._created_on = datetime.datetime.now().isoformat(timespec="microseconds")

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def created_on(self) -> str:
        return self._created_on


@dataclasses.dataclass
class CaseSelection:
    cases: list[TestCase]
    tag: str | None
    _sha256: str = dataclasses.field(init=False)
    _created_on: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        cases = sorted([case.id for case in self.cases])
        text = json.dumps({"tag": self.tag, "cases": cases})
        self._sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._created_on = datetime.datetime.now().isoformat(timespec="microseconds")

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def created_on(self) -> str:
        return self._created_on


class Session:
    def __init__(self) -> None:
        # Even through this function is not meant to be called, we declare types so that code
        # editors know what to work with.
        self.name: str
        self.root: Path
        self.work_dir: Path
        self.index_file: Path
        self.latest_file: Path
        self._cases: list[TestCase] | None
        raise RuntimeError("Use Session factory methods create and load")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def initialize_properties(self, *, anchor: Path, name: str) -> None:
        self.name = name
        self.root = anchor / self.name
        self.work_dir = self.root / "work"
        self._cases = None
        self.index_file = self.root / "index.json"
        self.latest_file = self.root / "latest.json"

    @staticmethod
    def is_session(path: Path) -> Path | None:
        return (path / session_tag).exists()

    @classmethod
    def create(cls, anchor: Path, selection: CaseSelection) -> "Session":
        self: Session = object.__new__(cls)
        ts = datetime.datetime.now().isoformat(timespec="microseconds")
        self.initialize_properties(anchor=anchor, name=ts.replace(":", "-"))
        if self.root.exists() or (self.root / session_tag).exists():
            raise SessionExistsError(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._cases = selection.cases
        for case in self._cases:
            case.set_workspace_properties(workspace=self.root.parent.parent, session=self.name)
        graph: dict[str, list[str]] = {c.id: [d.id for d in c.dependencies] for c in self._cases}
        paths: dict[str, str] = {}
        for case in self._cases:
            paths[case.id] = os.path.relpath(case.working_directory, str(self.root))
            for dep in case.dependencies:
                if dep.id not in graph:
                    # Dep lives outside of this session
                    paths[dep.id] = os.path.relpath(dep.working_directory, str(self.root))
        index = {
            "name": self.name,
            "created_on": ts,
            "selection": selection.tag,
            "cases": graph,
            "paths": paths,
        }
        self.dump_index(index)
        self.latest_file.write_text(json.dumps({}))
        self.update_latest(self._cases)
        self.populate_worktree()
        write_directory_tag(self.root / session_tag)
        # Dump a snapshot of the configuration used to create this session
        file = self.root / "config"
        with open(file, "w") as fh:
            config.dump_snapshot(fh)
        return self

    def load_index(self) -> dict[str, dict]:
        index = json.loads(self.index_file.read_text())
        return index

    def rebuild_index(self) -> bool:
        cases: list[TestCase] = []
        for file in self.work_dir.rglob("testcase.lock"):
            state = json.loads(file.read_text())
            case = testcase_from_state(state)
            cases.append(case)
        graph: dict[str, list[str]] = {c.id: [d.id for d in c.dependencies] for c in self._cases}
        paths: dict[str, str] = {}
        for case in cases:
            paths[case.id] = os.path.relpath(case.working_directory, str(self.root))
            for dep in case.dependencies:
                if dep.id not in graph:
                    # Dep lives outside of this session
                    paths[dep.id] = os.path.relpath(dep.working_directory, str(self.root))
        index = self.load_index()
        index["cases"].clear()
        index["cases"].update(graph)
        index["paths"].clear()
        index["paths"].update(paths)
        self.dump_index(index)
        return True

    def dump_index(self, index: dict[str, dict]) -> None:
        self.index_file.write_text(json.dumps(index, indent=2))

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
        if self._cases is None:
            self._cases = self.load_testcases()
        assert self._cases is not None
        return self._cases

    def populate_worktree(self) -> None:
        for case in self.cases:
            path = Path(case.working_directory)
            path.mkdir(parents=True)
            with open(case.lockfile, "w") as fh:
                case.dump(fh)

    def load_testcases(self, ids: list[str] | None = None) -> list[TestCase]:
        index = self.load_index()
        paths = {id: str(self.root / p) for id, p in index["paths"].items()}
        return load_testcases(index["cases"], paths, ids=ids)

    def get_ready(self, ids: list[str] | None) -> list[TestCase]:
        cases: list[TestCase]
        if ids is None:
            cases = self.cases
        elif self._cases is None:
            cases = self.load_testcases(ids=ids)
        else:
            cases = [case for case in self._cases if case.id in ids]
        ready: list[TestCase] = []
        for case in cases:
            if case.masked():
                continue
            elif ids is not None and case.id not in ids:
                continue
            ready.append(case)
        return ready

    def run(self, ids: list[str] | None = None) -> dict[str, Any]:
        # Since test cases run in subprocesses, we archive the config to the environment.  The
        # config object in the subprocess will read in the archive and use it to re-establish the
        # correct config
        config.archive(os.environ)
        cases = self.get_ready(ids=ids)
        if not cases:
            raise StopExecution("No tests to run", notests_exit_status)
        logger.info(f"@*{{Starting}} session {self.name}")
        start = time.monotonic()
        returncode: int = -1
        try:
            with working_dir(str(self.work_dir)):
                returncode = config.pluginmanager.hook.canary_runtests(cases=cases)
        finally:
            stop = time.monotonic()
            duration = stop - start
            logger.info(f"Finished session in {duration:.2f} s. with returncode {returncode}")
            for case in cases:
                case.refresh()
            self.update_latest(cases)
            return {"returncode": returncode, "cases": cases}

    def load_latest(self) -> dict[str, Any]:
        latest: dict[str, Any] = json.loads(self.latest_file.read_text())
        latest.setdefault("cases", {})
        return latest

    def dump_latest(self, latest: dict[str, Any]) -> None:
        assert "cases" in latest
        atomic_write(self.latest_file, json.dumps(latest, indent=2))

    def rebuild_latest(self) -> bool:
        cases: list[TestCase] = []
        for file in self.work_dir.rglob("testcase.lock"):
            state = json.loads(file.read_text())
            case = testcase_from_state(state)
            cases.append(case)
        # Clear the current latest
        latest = self.load_latest()
        latest["cases"].clear()
        self.dump_latest(latest)
        self.update_latest(cases)
        return True

    def update_latest(self, cases: list[TestCase]) -> bool:
        latest = self.load_latest()
        for case in cases:
            entry = {
                "name": case.display_name,
                "fullname": case.fullname,
                "family": case.family,
                "returncode": case.returncode,
                "duration": case.duration,
                "started_on": timestamp_to_isoformat(case.start),
                "finished_on": timestamp_to_isoformat(case.stop),
                "working_directory": case.working_directory,
                "execution_directory": case.execution_directory,
                "instance_attributes": case.instance_attributes,
                "status": {"value": case.status.value, "details": case.status.details},
            }
            latest["cases"][case.id] = entry
        self.dump_latest(latest)
        return True

    def enter(self) -> None: ...

    def exit(self) -> None: ...


class Workspace:
    version_info = (1, 0, 0)

    def __init__(self, anchor: str | Path = Path.cwd()) -> None:
        # Even through this function is not meant to be called, we declare types so that code
        # editors know what to work with.
        self.root: Path

        self.view: Path | None

        # "Immutable" objects
        self.objects_dir: Path
        self.casespecs_dir: Path
        self.generators_dir: Path

        # Storage for pointers to test sessions
        self.refs_dir: Path

        # Storage for test sessions
        self.sessions_dir: Path

        # Mutable data
        self.cache_dir: Path

        # Storage for CaseSelection tags
        self.tags_dir: Path

        # Text logs
        self.logs_dir: Path

        # Pointer to latest session
        self.head: Path

        self.lockfile: Path
        self.index_file: Path
        self.latest_file: Path

        raise RuntimeError("Use Workspace factory methods create and load")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def initialize_properties(self, *, anchor: Path) -> None:
        self.root = anchor / workspace_path
        self.view = None
        self.objects_dir = self.root / "objects"
        self.casespecs_dir = self.objects_dir / "specs"
        self.generators_dir = self.objects_dir / "generators"
        self.refs_dir = self.root / "refs"
        self.sessions_dir = self.root / "sessions"
        self.cache_dir = self.root / "cache"
        self.tags_dir = self.root / "tags"
        self.logs_dir = self.root / "logs"
        self.head = self.root / "HEAD"
        self.lockfile = self.root / "lock"
        self.latest_file = self.root / "latest.json"
        self.index_file = self.root / "index.jsons"

    @staticmethod
    def remove(start: str | Path = Path.cwd()) -> Path | None:
        anchor = Workspace.find_anchor(start=start)
        if anchor is None:
            return
        workspace = anchor / workspace_path
        view: Path | None = None
        cache_dir = workspace / "cache"
        file = workspace / "cache/view"
        if file.exists():
            relpath = file.read_text().strip()
            view = cache_dir / relpath
        if view is None:
            if (workspace / workspace_tag).exists():
                force_remove(workspace)
            return workspace
        elif (workspace / workspace_tag).exists() and (view / view_tag).exists():
            force_remove(view)
            force_remove(workspace)
            return workspace
        elif (workspace / workspace_tag).exists() and view.exists():
            raise ValueError(f"Cannot remove {workspace} because {view} is not owned by Canary")
        else:
            logger.warning(f"Unable to remove {workspace}")
            return None

    @staticmethod
    def find_anchor(start: str | Path = Path.cwd()) -> Path | None:
        current_path = Path(start).absolute()
        if current_path.stem == workspace_path:
            return current_path.parent
        while True:
            if (current_path / workspace_path).exists():
                return current_path
            if current_path.parent == current_path:
                break
            current_path = current_path.parent
        return None

    @staticmethod
    def find_workspace(start: str | Path = Path.cwd()) -> Path | None:
        if anchor := Workspace.find_anchor(start=start):
            return anchor / workspace_path
        return None

    @classmethod
    def create(cls, path: str | Path = Path.cwd(), force: bool = False) -> "Workspace":
        path = Path(path).absolute()
        if path.stem == workspace_path:
            raise ValueError(f"Don't include {workspace_path} in workspace path")
        if force:
            cls.remove(start=path)
        self: Workspace = object.__new__(cls)
        self.initialize_properties(anchor=path)
        if self.root.exists():
            raise WorkspaceExistsError(path)
        self.root.mkdir(parents=True)
        write_directory_tag(self.root / workspace_tag)

        self.casespecs_dir.mkdir(parents=True)
        self.generators_dir.mkdir(parents=True)
        self.refs_dir.mkdir(parents=True)
        self.sessions_dir.mkdir(parents=True)
        self.cache_dir.mkdir(parents=True)
        self.tags_dir.mkdir(parents=True)
        self.tag("default")
        self.logs_dir.mkdir(parents=True)
        version = self.root / "VERSION"
        version.write_text(".".join(str(_) for _ in self.version_info))

        file = self.logs_dir / "canary-log.txt"
        logging.add_file_handler(str(file), logging.TRACE)

        if var := config.get("config:view"):
            if isinstance(var, str):
                self.view = (self.root.parent / var).resolve()
            else:
                self.view = (self.root.parent / "TestResults").resolve()
            if self.view.exists():
                raise FileExistsError(
                    f"Canary requires ownership of existing directory {self.view}. "
                    f"Rename {self.view} and try again."
                )
            self.view.mkdir(parents=True)
            write_directory_tag(self.view / view_tag)
            file = self.cache_dir / "view"
            link = os.path.relpath(str(self.view), str(file.parent))
            file.write_text(link)

        self.latest_file.write_text(json.dumps({}))

        file = self.root / "canary.yaml"
        file.write_text(json.dumps({}))
        scope = config.ConfigScope("workspace", str(file), {})
        config.push_scope(scope)
        return self

    @classmethod
    def load(cls, start: str | Path = Path.cwd()) -> "Workspace":
        anchor = cls.find_anchor(start=start)
        if anchor is None:
            raise NotAWorkspaceError(
                f"not a Canary session (or any of its parent directories): {workspace_path}"
            )
        self: Workspace = object.__new__(cls)
        self.initialize_properties(anchor=anchor)
        file = self.cache_dir / "view"
        if file.exists():
            relpath = file.read_text().strip()
            self.view = (self.cache_dir / relpath).resolve()
            self.view.mkdir(parents=True, exist_ok=True)
            view_file = self.view / view_tag
            if not view_file.exists():
                write_directory_tag(view_file)
        file = self.logs_dir / "canary-log.txt"
        logging.add_file_handler(str(file), logging.TRACE)
        return self

    def sessions(self) -> Generator[Session, None, None]:
        for path in self.sessions_dir.iterdir():
            if Session.is_session(path):
                yield Session.load(path)

    @contextmanager
    def session(
        self, selection: CaseSelection | None = None, name: str | None = None
    ) -> Generator[Session, None, None]:
        session: Session
        if selection is not None and name is not None:
            raise TypeError("Mutually exlusive keyword arguments: 'selection', 'name'")
        elif selection is None and name is None:
            raise TypeError("Missing required keyword arguments: 'selection' or 'name'")
        if selection is not None:
            session = Session.create(self.sessions_dir, selection)
        else:
            root = self.sessions_dir / name
            if not Session.is_session(root):
                raise NotASessionError(name)
            session = Session.load(root)
        try:
            yield session
        finally:
            self.update(session)

    def load_latest(self) -> dict[str, Any]:
        latest: dict[str, Any] = json.loads(self.latest_file.read_text())
        latest.setdefault("cases", {})
        return latest

    def dump_latest(self, latest: dict[str, Any]) -> None:
        assert "cases" in latest
        atomic_write(self.latest_file, json.dumps(latest, indent=2))

    def update(self, session: Session) -> None:
        """Update latest results, view, and refs with results from ``session``"""
        latest = self.load_latest()
        results = latest["cases"]
        session_latest = session.load_latest()
        view_entries: dict[str, list[str]] = {}
        for id, their_entry in session_latest["cases"].items():
            if id in results:
                # Determine if this session's results are newer than my results
                # They can be older if only a subset of the session's cases were run this last time
                if results[id]["finished_on"] != "NA":
                    my_time = datetime.datetime.fromisoformat(results[id]["finished_on"])
                    their_time = datetime.datetime.fromisoformat(their_entry["finished_on"])
                    if my_time > their_time:
                        continue
            my_entry = {"session": session.name, **their_entry}
            results[id] = my_entry
            relpath = Path(their_entry["working_directory"]).relative_to(session.work_dir)
            view_entries.setdefault(session.work_dir, []).append(relpath)

        self.dump_latest(latest)
        self._update_view(view_entries)

        # Write meta data file refs/latest -> ../sessions/{session.root}
        file = self.refs_dir / "latest"
        file.unlink(missing_ok=True)
        link = os.path.relpath(str(session.root), str(file.parent))
        file.write_text(str(link))

        # Write meta data file HEAD -> ./sessions/{session.root}
        self.head.unlink(missing_ok=True)
        link = os.path.relpath(str(file), str(self.head.parent))
        self.head.write_text(str(link))

    def rebuild_view(self) -> None:
        if self.view is None:
            return
        logger.info(f"Rebuilding view at {self.view}")
        latest = self.load_latest()
        results = latest["cases"]
        view_entries: dict[str, list[str]] = {}
        for path in self.view.iterdir():
            if path.is_dir():
                force_remove(path)
        for session in self.sessions():
            session_latest = session.load_latest()
            for id, their_entry in session_latest["cases"].items():
                if id in results:
                    # Determine if this session's results are newer than my results
                    # They can be older if only a subset of the session's cases were run this last time
                    my_entry = results[id]
                    if my_entry["finished_on"] != "NA":
                        my_time = datetime.datetime.fromisoformat(my_entry["finished_on"])
                        their_time = datetime.datetime.fromisoformat(their_entry["finished_on"])
                        if my_time > their_time:
                            continue
                my_entry = {"session": session.name, **their_entry}
                relpath = Path(their_entry["working_directory"]).relative_to(session.work_dir)
                view_entries.setdefault(session.work_dir, []).append(relpath)
        self._update_view(view_entries)
        logger.info("Done rebuilding view")

    def _update_view(self, view_entries: dict[Path, list[Path]]) -> None:
        logger.info(f"Updating view at {self.view}")
        if self.view is None:
            return
        for root, paths in view_entries.items():
            for path in paths:
                target = root / path
                link = self.view / path
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists():
                    link.unlink()
                link.symlink_to(target)

    def is_tag(self, name: str) -> bool:
        """Is ``name`` a tag?"""
        for p in self.tags_dir.iterdir():
            if p.name == name:
                return True
        return False

    def inside_view(self, path: Path | str) -> bool:
        """Is ``path`` inside of a self.view?"""
        if self.view is None:
            return False
        return Path(path).absolute().is_relative_to(self.view)

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
            "workspace_version": (self.root / "VERSION").read_text().strip(),
        }
        return info

    def _add_generator(self, generator: AbstractTestGenerator) -> int:
        file = self.generators_dir / generator.id[:2] / f"{generator.id[2:]}.json"
        if file.exists():
            logger.debug(f"Test case generator already in workspace ({generator})")
            return 0
        file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(file, json.dumps(generator.getstate(), indent=2))
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

    def active_testcases(self) -> list[TestCase]:
        cases = self.load_testcases(latest=True)
        return [case for case in cases if case.session is not None]

    def add(
        self, scan_paths: dict[str, list[str]], pedantic: bool = True
    ) -> list[AbstractTestGenerator]:
        """Find test case generators in scan_paths and add them to this workspace"""
        generators: list[AbstractTestGenerator] = []
        for root, paths in scan_paths.items():
            p = ScanPath(root=root, paths=paths)
            generators.extend(config.pluginmanager.hook.canary_collect_generators(scan_path=p))
        n: int = 0
        for generator in generators:
            n += self._add_generator(generator)
        # Invalidate caches
        warned = False
        if (self.cache_dir / "select").exists():
            for file in (self.cache_dir / "select").iterdir():
                if not file.is_file():
                    continue
                if not warned:
                    logger.info("Invalidating previously locked test case cache")
                    warned = True
                with open(file, "rb") as fh:
                    selection = pickle.load(fh)
                    selection.specs = None
                with open(file, "wb") as fh:
                    pickle.dump(selection, file)
        logger.info(f"@*{{Added}} {n} new test case generators to {self.root}")
        return generators

    def load_testcases(self, ids: list[str] | None = None, latest: bool = False) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed.  If ``latest is True``,
        update each case to point to the latest run instance.
        """
        index = self.load_index()
        paths: dict[str, str] = {}
        for id in index:
            paths[id] = os.path.join(self.casespecs_dir, id[:2], id[2:])
        if ids:
            expand_ids(ids, list(index.keys()))
        cases = load_testcases(index, paths, ids=ids)
        if not latest:
            return cases
        self.update_testcases_with_newest_results(cases)
        return cases

    def load_specs(self, ids: list[str] | None = None) -> list[testspec.ResolvedSpec]:
        """Load cached test specs.  Dependency resolution is performed.  If ``latest is True``,
        update each case to point to the latest run instance.
        """
        index = self.load_index()
        files: list[Path] = []
        for id in index:
            files.append(self.casespecs_dir / id[:2] / id[2:] / "spec.lock")
        if ids:
            expand_ids(ids, list(index.keys()))
        specs = testspec.load(files, ids=ids)
        return specs

    def get_testcases_by_spec(self, case_specs: list[str], tag: str | None = None) -> CaseSelection:
        ids = [_[1:] for _ in case_specs]
        cases = self.load_testcases(ids=ids)
        selection = CaseSelection(cases, tag)
        if tag is not None:
            self.cache_selection(selection)
        return selection

    def update_testcases_with_newest_results(self, cases: list[TestCase]) -> None:
        """Update cases in ``cases`` with their latest results"""
        latest = self.load_latest()
        results: dict[str, dict] = latest["cases"]
        for case in cases:
            if result := results.get(case.id):
                print(result)
                if session := result["session"]:
                    attrs = {
                        "session": session,
                        "workspace": str(self.root),
                        "start": datetime.datetime.fromisoformat(result["started_on"]).timestamp(),
                        "stop": datetime.datetime.fromisoformat(result["finished_on"]).timestamp(),
                        "status": result["status"],
                        "returncode": result["returncode"],
                        "instance_attributes": result["instance_attributes"],
                    }
                    case.update(**attrs)

    @staticmethod
    def filter(
        cases: list[TestCase],
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        regex: str | None = None,
        start: str | None = None,
        case_specs: list[str] | None = None,
    ) -> None:
        """Filter test cases (mask test cases that don't meet a specific criteria)

        Args:
          keyword_exprs: Include those tests matching this keyword expressions
          parameter_expr: Include those tests matching this parameter expression
          start: The starting directory the python session was invoked in
          case_specs: Include those tests matching these specs

        Returns:
          A list of test cases

        """
        config.pluginmanager.hook.canary_testsuite_mask(
            cases=cases,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            case_specs=case_specs,
            start=start,
            ignore_dependencies=False,
        )

    def tag(self, name: str, **meta: Any) -> str:
        tag_file = self.tags_dir / name
        if tag_file.exists():
            raise ValueError(f"Tag {name!r} already exists")
        cache_file = self.cache_dir / "tags" / name
        link = os.path.relpath(str(cache_file), str(tag_file.parent))
        tag_file.write_text(str(link))
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(meta, indent=2))
        return name

    def remove_tag(self, name: str) -> bool:
        if name == "default":
            logger.error("Cannot remove default tag")
            return False
        tag_file = self.tags_dir / name
        if not tag_file.exists():
            logger.warning(f"Tag {name} does not exist")
            return False
        tag_file.unlink()
        cache_file = self.cache_dir / "tags" / name
        cache_file.unlink(missing_ok=True)
        cache_file = self.cache_dir / "select" / name
        cache_file.unlink(missing_ok=True)
        return True

    def tag_info(self, name: str) -> dict[str, Any]:
        tag_file = self.tags_dir / name
        if not tag_file.exists():
            raise ValueError(f"Tag {name} does not exist")
        link = tag_file.read_text().strip()
        cache_file = self.cache_dir / link
        meta: dict[str, Any] = json.loads(cache_file.read_text())
        return meta

    def lock(
        self,
        *,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        on_options: list[str] | None = None,
        regex: str | None = None,
        case_specs: list[str] | None = None,
        **kwargs: Any,
    ) -> list[testspec.TestSpec]:
        """Generate (lock) test specs from generators

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
          A list of test specs

        """
        # FIXME: Look into locking the latest, we used to do this.
        specs: list[testspec.ResolvedSpec]
        generators = self.load_testcase_generators()
        meta = {"f": sorted([str(generator.file) for generator in generators]), "o": on_options}
        sha = hashlib.sha256(json.dumps(meta).encode("utf-8")).hexdigest()
        file = self.cache_dir / "lock" / sha[:20]
        if file.exists():
            logger.debug("Reading test specs from cache")
            specs = self.load_specs()
        else:
            logger.debug("Generating test specs")
            specs = testspec.generate_specs(generators, on_options=on_options)
            for spec in specs:
                # Add all test specs to the object store before masking so that future stages don't
                # inherit this stage's mask (if any)
                self.add_spec(spec)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.touch()

        ids: list[str] | None = None
        if case_specs:
            ids = [_[1:] for _ in case_specs]

        testspec.apply_masks(
            specs,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            ids=ids,
        )
        for spec in static_order(specs):
            config.pluginmanager.hook.canary_testcase_modify(case=spec)

        final = testspec.finalize(specs)
        config.pluginmanager.hook.canary_collectreport(cases=final)

        selected = [spec for spec in final if not spec.mask]
        if not selected:
            logger.warning("Empty test spec selection")

        return selected

    def cache_selection(self, selection: SpecSelection) -> None:
        assert selection.tag is not None
        cache_file = self.cache_dir / "select" / selection.tag
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "wb") as fh:
            pickle.dump(selection, fh)

    def make_selection(
        self,
        tag: str | None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        on_options: list[str] | None = None,
        case_specs: list[str] | None = None,
        regex: str | None = None,
    ) -> CaseSelection:
        logger.info("@*{Selecting} test cases from generators")
        kwds = dict(
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            on_options=on_options,
            case_specs=case_specs,
            regex=regex,
        )
        if tag is None and all(not value for value in kwds.values()):
            # This is the default selection
            return self.get_selection("default")
        if tag is not None:
            # Tag early to error out before locking if tag already exists
            self.tag(tag, **kwds)
        try:
            specs = self.lock(**kwds)
            selection = SpecSelection(specs=specs, tag=tag)
            if tag is not None:
                self.cache_selection(selection)
        except Exception:
            if tag is not None:
                self.remove_tag(tag)
            raise
        return selection

    def get_selection(self, tag: str = "default") -> SpecSelection:
        tag_file = self.tags_dir / tag
        if not tag_file.exists():
            raise ValueError(f"Tag {tag} does not exist")

        selection: CaseSelection

        cache_file = self.cache_dir / "select" / tag
        if not cache_file.exists():
            link = tag_file.read_text().strip()
            meta = json.loads((self.tags_dir / link).read_text())
            specs = self.lock(**meta)
            selection = SpecSelection(specs=specs, tag=tag)
            self.cache_selection(selection)
            return selection

        with open(cache_file, "rb") as fh:
            selection = pickle.load(fh)

        if selection.specs:
            return selection

        # No cases: cache was invalidated at some point
        link = tag_file.read_text().strip()
        meta = json.loads((self.tags_dir / link).read_text())
        specs = self.lock(**meta)
        selection = SpecSelection(specs=specs, tag=tag_file.name)
        self.cache_selection(selection)
        return selection

    def add_spec(self, spec: testspec.ResolvedSpec) -> None:
        file = self.casespecs_dir / spec.id[:2] / spec.id[2:] / "spec.lock"
        if file.exists():
            return
        file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(file, spec.dumps(indent=2))
        with self.index_file.open(mode="a") as fh:
            fh.write(json.dumps({spec.id: [dep.id for dep in spec.dependencies]}) + "\n")
        latest = self.load_latest()
        if spec.id not in latest["cases"]:
            latest["cases"][spec.id] = {
                "name": spec.display_name,
                "fullname": spec.fullname,
                "family": spec.family,
                "returncode": -1,
                "duration": -1,
                "started_on": "NA",
                "finished_on": "NA",
                "working_directory": None,
                "execution_directory": None,
                "instance_attributes": None,
                "status": {"value": "created", "details": None},
            }
        self.dump_latest(latest)

    def statusinfo(self) -> dict[str, list[str]]:
        latest = self.load_latest()
        info: dict[str, list[str]] = {}
        for id, entry in latest["cases"].items():
            info.setdefault("id", []).append(id[:7])
            info.setdefault("name", []).append(entry["name"])
            info.setdefault("fullname", []).append(entry["fullname"])
            info.setdefault("family", []).append(entry["family"])
            info.setdefault("session", []).append(entry["session"])
            info.setdefault("returncode", []).append(entry["returncode"])
            info.setdefault("duration", []).append(entry["duration"])
            info.setdefault("status_value", []).append(entry["status"]["value"])
            if entry["session"] is None and not entry["status"]["details"]:
                entry["status"]["details"] = "Test case not included in any session"
            info.setdefault("status_details", []).append(entry["status"]["details"] or "")
        return info

    def collect_all_testcases(self) -> Generator[TestCase, None, None]:
        for session in self.sessions():
            yield from session.cases

    def gc(self, dryrun: bool = False) -> None:
        """Garbage collect"""
        logger.info(f"Garbage collecting {self.root}")
        removed: int = 0
        try:
            allcases = list(self.collect_all_testcases())
            removable = find_removable_cases(allcases)
            for case in removable:
                if Path(case.working_directory).exists():
                    removed += 1
                    logger.info(f"gc: removing {case}::{case.session}")
                    if dryrun:
                        continue
                    else:
                        case.teardown()
        finally:
            if not dryrun:
                self.rebuild_latest()
                self.rebuild_view()
        logger.info(f"Garbage collected {removed} test cases")

    def rebuild_latest(self) -> bool:
        "Rebuild latest.json and self.view"
        logger.info("Rebuilding test results database")
        for session in self.sessions():
            session.rebuild_latest()
        latest = self.load_latest()
        latest["cases"].clear()
        for session in self.sessions():
            session_latest = session.load_latest()
            for case_id, their_entry in session_latest["cases"].items():
                if case_id in latest["cases"]:
                    # Determine if this session's results are newer than my results
                    # They can be older if only a subset of the session's cases were run this last time
                    my_entry = latest["cases"][case_id]
                    if my_entry["finished_on"] != "NA":
                        my_time = datetime.datetime.fromisoformat(my_entry["finished_on"])
                        their_time = datetime.datetime.fromisoformat(their_entry["finished_on"])
                        if my_time > their_time:
                            continue
                my_entry = {"session": session.name, **their_entry}
                latest["cases"][case_id] = my_entry
        self.dump_latest(latest)
        return True

    def load_index(self) -> dict[str, list[str]]:
        """Load the test cases index"""
        # index format: {ID: [DEPS_IDS]}
        index: dict[str, list[str]] = {}
        for line in self.index_file.read_text().splitlines():
            entry = json.loads(line)
            index.update(entry)
        return index

    def locate(self, *, case: str | None = None) -> Any:
        """Locate something in the workspace"""
        if case is not None:
            return self.locate_testcase(case)

    def locate_testcase(self, spec: str) -> TestCase:
        case: TestCase
        if spec.startswith("/"):
            latest = self.load_latest()
            for id in latest.keys():
                if id.startswith(spec[1:]):
                    break
            else:
                raise ValueError(f"{spec}: no matching test found in {self.root}")
            lockfile = self.casespecs_dir / id[:2] / id[2:] / TestCase._lockfile
            state = json.loads(lockfile.read_text())
            case = testcase_from_state(state)
        else:
            cases = self.load_testcases()
            for case in cases:
                if case.matches(spec):
                    break
            else:
                raise ValueError(f"{spec}: no matching test found in {self.root}")
        self.update_testcases_with_newest_results([case])
        return case


def load_testcases(
    graph: dict[str, list[str]],
    paths: dict[str, str],
    ids: list[str] | None = None,
) -> list[TestCase]:
    """Load cached test cases.  Dependency resolution is performed.

    Args:
      graph: graph[case.id] are the dependencies of case
      paths: path[case.id] is the working directory for case
      ids: only return these ids

    Returns:
      Loaded test cases
    """
    ids_to_load: set[str] = set()
    casemap: dict[str, TestCase | TestMultiCase] = {}
    if ids:
        # we must not only load the requested IDs, but also their dependencies
        for id in ids:
            ids_to_load.update(find_reachable_nodes(graph, id))
    ts: TopologicalSorter = TopologicalSorter()
    for id, deps in graph.items():
        ts.add(id, *deps)
    for id in ts.static_order():
        if ids_to_load and id not in ids_to_load:
            continue
        # see TestCase.lockfile for file pattern
        file = Path(os.path.join(paths[id], TestCase._lockfile))
        state = json.loads(file.read_text())
        for i, dep_state in enumerate(state["properties"]["dependencies"]):
            # assign dependencies from existing dependencies
            state["properties"]["dependencies"][i] = casemap[dep_state["properties"]["id"]]
        casemap[id] = testcase_from_state(state)
        assert id == casemap[id].id
    return list(casemap.values())


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


def atomic_write(path: Path, text: str) -> None:
    dir = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def timestamp_to_isoformat(arg: float) -> str:
    return datetime.datetime.fromtimestamp(arg).isoformat(timespec="microseconds")


def write_directory_tag(file: Path) -> None:
    file.write_text(
        "Signature: 8a477f597d28d172789f06886806bc55\n"
        "# This file is a directory tag automatically created by canary.\n"
    )


def expand_ids(ids: list[str], index: list[str]) -> None:
    for i, id in enumerate(ids):
        if id not in index:
            # Expand to full length
            for ix in index:
                if ix.startswith(id):
                    ids[i] = ix
                    break
            else:
                raise ValueError(f"ID for {id} not found")


def find_removable_cases(cases: list[TestCase]) -> list[TestCase]:
    """Identify testcases eligible for garbage collection

    A test case can be removed if:
      1. Its status is "success"
      2. All its dependencies (if any) are successful
      3. No test cases with non-success status depends on it (directly or indirectly)

    """
    # Use id(case), not the case directly since the case's __hash__ is derived from case.id
    # and the list of cases could have multiple cases with the same ID across multiple
    # sessions
    okstats = ("success", "xfail", "xdiff")
    case_by_id: dict[int, TestCase] = {id(case): case for case in cases}
    failed_cases: set[int] = {id(case) for case in cases if not case.status.satisfies(okstats)}
    dependents: dict[int, set[int]] = {id(case): set() for case in cases}
    for case in cases:
        for dep in case.dependencies:
            dependents[id(dep)].add(id(case))
    needed: set[int] = set(failed_cases)
    stack: list[TestCase] = [case for case in cases if id(case) not in failed_cases]
    while stack:
        case = stack.pop()
        for dep in case.dependencies:
            dep_id = id(dep)
            if dep_id not in needed:
                needed.add(dep_id)
                stack.append(dep)
    removable: list[TestCase] = []
    for case in cases:
        if not case.status.satisfies(okstats):
            continue
        if id(case) in needed:
            continue
        if any(not dep.status.satisfies(okstats) for dep in case.dependencies):
            continue
        removable.append(case)
    return removable


class WorkspaceExistsError(Exception):
    pass


class NotAWorkspaceError(Exception):
    pass


class NotASessionError(Exception):
    pass


class SessionExistsError(Exception):
    pass
