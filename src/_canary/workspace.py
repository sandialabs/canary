# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import collections
import dataclasses
import datetime
import fnmatch
import hashlib
import os
import pickle  # nosec B403
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Sequence
from typing import TypeVar

import yaml

from . import config
from . import rules
from . import select
from . import testspec
from .collect import Collector
from .error import StopExecution
from .error import notests_exit_status
from .generate import Generator
from .generator import AbstractTestGenerator
from .runtest import Runner
from .runtest import canary_runtests
from .status import Status
from .testcase import Measurements
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import ResolvedSpec
from .timekeeper import Timekeeper
from .util import json_helper as json
from .util import logging
from .util.filesystem import async_rmtree
from .util.filesystem import force_remove
from .util.filesystem import write_directory_tag
from .util.graph import static_order
from .util.names import unique_random_name
from .version import __static_version__

logger = logging.get_logger(__name__)

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
view_tag = "VIEW.TAG"


DB_MAX_RETRIES = 8
DB_BASE_DELAY = 0.05  # 50ms base for exponential backoff (0.05, 0.1, 0.2, ...)
SQL_CHUNK_SIZE = 900


@dataclasses.dataclass
class Session:
    name: str
    cases: list[TestCase]
    prefix: Path
    returncode: int = dataclasses.field(init=False, default=-1)
    started_on: datetime.datetime = dataclasses.field(init=False, default=datetime.datetime.min)
    finished_on: datetime.datetime = dataclasses.field(init=False, default=datetime.datetime.min)

    def __post_init__(self) -> None:
        for case in self.cases:
            if case.mask:
                raise ValueError(f"{case}: unexpectedly masked test case")

    def run(self, workspace: "Workspace") -> None:
        self.prefix.mkdir(parents=True, exist_ok=True)
        ready = [case for case in self.cases if case.status.state in ("READY", "PENDING")]
        runner = Runner(ready, self.name, workspace=workspace)
        if not ready:
            raise StopExecution("no cases to run", exit_code=notests_exit_status)
        starting_dir = os.getcwd()
        try:
            self.started_on = datetime.datetime.now()
            os.chdir(str(self.prefix))
            canary_runtests(runner=runner)
        except Exception:
            logger.exception("session run failed")
            self.returncode = 1
        finally:
            self.finished_on = datetime.datetime.now()
            os.chdir(starting_dir)
            self.returncode = runner.returncode


class Workspace:
    version_info = (1, 0, 0)

    def __init__(self, anchor: str | Path = Path.cwd()) -> None:
        # Even through this function is not meant to be called, we declare types so that code
        # editors know what to work with.
        self.root: Path

        self.view: Path | None

        # Storage for pointers to test sessions
        self.refs_dir: Path

        # Storage for test sessions
        self.sessions_dir: Path

        # Mutable data
        self.cache_dir: Path

        # Temporary data
        self.tmp_dir: Path

        # Text logs
        self.logs_dir: Path

        # Pointer to latest session
        self.head: Path

        self.dbfile: Path
        self.db: WorkspaceDatabase

        raise RuntimeError("Use Workspace factory methods create and load")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def initialize_properties(self, *, anchor: Path) -> None:
        self.root = anchor / workspace_path
        self.view = None
        self.refs_dir = self.root / "refs"
        self.sessions_dir = self.root / "sessions"
        self.cache_dir = self.root / "cache"
        self.tmp_dir = self.root / "tmp"
        self.logs_dir = self.root / "logs"
        self.head = self.root / "HEAD"
        self.dbfile = self.root / "workspace.sqlite3"

    @staticmethod
    def remove(start: str | Path = Path.cwd()) -> Path | None:
        relpath = Path(start).absolute().relative_to(Path.cwd())
        pm = logger.progress_monitor(f"[bold]Removing[/bold] workspace from {relpath}")
        anchor = Workspace.find_anchor(start=start)
        if anchor is None:
            pm.done("no workspace found")
            return None
        workspace = anchor / workspace_path
        view: Path | None = None
        cache_dir = workspace / "cache"
        file = workspace / "cache/view"
        if file.exists():
            relpath = Path(file.read_text().strip())
            view = cache_dir / relpath
        if view is None:
            if (workspace / workspace_tag).exists():
                force_remove(workspace)
            pm.done()
            return workspace
        elif (workspace / workspace_tag).exists() and (view / view_tag).exists():
            force_remove(view)
            force_remove(workspace)
            pm.done()
            return workspace
        elif (workspace / workspace_tag).exists() and view.exists():
            raise ValueError(f"Cannot remove {workspace} because {view} is not owned by Canary")
        else:
            pm.done(f"error: unable to remove {workspace}")
            return None

    def rmf(self) -> None:
        # This is dangerous!!!
        if self.view:
            async_rmtree(self.view)
        async_rmtree(self.root)

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
        logger.info(f"[bold]Initializing[/] empty canary workspace at {path}")
        self: Workspace = object.__new__(cls)
        self.initialize_properties(anchor=path)
        if self.root.exists():
            logger.error("workspace already exists")
            raise WorkspaceExistsError(path)
        self.root.mkdir(parents=True)
        write_directory_tag(self.root / workspace_tag)

        self.refs_dir.mkdir(parents=True)
        self.sessions_dir.mkdir(parents=True)
        self.cache_dir.mkdir(parents=True)
        self.tmp_dir.mkdir(parents=True)
        self.logs_dir.mkdir(parents=True)
        version = self.root / "VERSION"
        version.write_text(".".join(str(_) for _ in self.version_info))

        file = self.logs_dir / "canary-log.txt"
        logging.add_file_handler(str(file), logging.TRACE)

        if var := config.get("workspace:view"):
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

        self.db = WorkspaceDatabase.create(self.dbfile)
        file = self.root / "config.yaml"
        cfg: dict[str, Any] = {}
        if mods := config.getoption("config_mods"):
            cfg.update(mods)
        with open(file, "w") as fh:
            yaml.dump({"canary": cfg}, fh, default_flow_style=False)

        return self

    @classmethod
    def load(cls, start: str | Path | None = None) -> "Workspace":
        start = Path(start or Path.cwd())
        logger.debug(f"Loading Canary workspace from {start}")
        anchor = cls.find_anchor(start=start)
        if anchor is None:
            raise NotAWorkspaceError(
                f"not a Canary workspace (or any of its parent directories): {workspace_path}"
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
        self.db = WorkspaceDatabase.load(self.dbfile)
        return self

    def run(
        self,
        specs: list["ResolvedSpec"],
        reuse_session: bool | str = False,
        update_view: bool = True,
        only: str = "not_pass",
    ) -> Session:
        now = datetime.datetime.now()
        session_name: str
        if isinstance(reuse_session, str):
            session_name = reuse_session
        else:
            session_name = now.isoformat(timespec="microseconds").replace(":", "-")
        session_dir = self.sessions_dir / session_name
        cases = self.construct_testcases(specs, session_dir)
        selector = select.RuntimeSelector(cases, workspace=self.root)
        selector.add_rule(rules.ResourceCapacityRule())
        selector.add_rule(rules.RerunRule(strategy=only))
        selector.run()

        # At this point, test cases have been reconstructed and, if previous results exist,
        # restored to their last ran state.  If reuse_session is True, we leave the test case as
        # is.  Otherwise, we swap out the old session for the new.
        ready: list["TestCase"] = []
        for case in cases:
            if case.mask:
                continue
            elif not reuse_session:
                case.workspace.root = session_dir
                case.workspace.session = session_dir.name
            ready.append(case)

        session = Session(name=session_dir.name, prefix=session_dir, cases=ready)
        config.pluginmanager.hook.canary_sessionstart(session=session)
        session.run(workspace=self)
        config.pluginmanager.hook.canary_sessionfinish(session=session)
        self.add_session_results(session, update_view=update_view)
        return session

    def add_session_results(self, results: Session, update_view: bool = True) -> None:
        """Update latest results, view, and refs with results from ``session``"""
        self.db.put_results(results)

        if update_view:
            view_entries: dict[Path, list[Path]] = {}
            for case in results.cases:
                if case.workspace.session is not None:
                    prefix = self.sessions_dir / case.workspace.session
                else:
                    prefix = results.prefix
                relpath = case.workspace.dir.relative_to(prefix)
                view_entries.setdefault(prefix, []).append(relpath)
            self.update_view(view_entries)

        # Write meta data file refs/latest -> ../sessions/{session.root}
        file = self.refs_dir / "latest"
        file.unlink(missing_ok=True)
        link = os.path.relpath(str(results.prefix), str(file.parent))
        file.write_text(str(link))

        # Write meta data file HEAD -> ./sessions/{session.root}
        self.head.unlink(missing_ok=True)
        link = os.path.relpath(str(file), str(self.head.parent))
        self.head.write_text(str(link))

    def rebuild_view(self) -> None:
        """Keep only the latet results"""
        if not self.view:
            return
        logger.info(f"Rebuilding view at {self.root}")
        view: dict[str, tuple[str, str]] = {}
        latest = self.db.get_results()
        for id, data in latest.items():
            dir = self.sessions_dir / data["session"] / data["workspace"]
            relpath = dir.relative_to(self.sessions_dir / data["session"])
            view[id] = (str(self.sessions_dir / data["session"]), str(relpath))
        for path in self.view.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
        view_entries: dict[Path, list[Path]] = {}
        for root, p in view.values():
            view_entries.setdefault(Path(root), []).append(Path(p))
        self.update_view(view_entries)

    def update_view(self, view_entries: dict[Path, list[Path]]) -> None:
        logger.info(f"[bold]Updating[/] view at {self.view}")
        if self.view is None:
            return
        for root, paths in view_entries.items():
            for path in paths:
                target = root / path
                link = self.view / path
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists():
                    link.unlink()
                try:
                    link.symlink_to(target, target_is_directory=True)
                except FileExistsError:
                    pass

    def inside_view(self, path: Path | str) -> bool:
        """Is ``path`` inside of a self.view?"""
        if self.view is None:
            return False
        return Path(path).absolute().is_relative_to(self.view)

    def info(self) -> dict[str, Any]:
        latest_session: str | None = None
        if (self.refs_dir / "latest").exists():
            link = (self.refs_dir / "latest").read_text().strip()
            path = self.refs_dir / link
            latest_session = path.stem
        info = {
            "root": str(self.root),
            "session_count": len([p for p in self.sessions_dir.glob("*") if p.is_dir()]),
            "latest_session": latest_session,
            "tags": self.db.tags,
            "version": __static_version__,
            "workspace_version": (self.root / "VERSION").read_text().strip(),
        }
        return info

    def create_selection(
        self,
        tag: str | None,
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["ResolvedSpec"]:
        """Find test case generators in scan_paths and add them to this workspace"""
        tag = tag or unique_random_name(self.db.tags)
        collector = Collector()
        collector.add_scanpaths(scanpaths)
        generators = collector.run()
        signature, resolved = self.generate_testspecs(generators=generators, on_options=on_options)
        selector = select.Selector(resolved, self.root)
        if keyword_exprs:
            selector.add_rule(rules.KeywordRule(keyword_exprs))
        if parameter_expr:
            selector.add_rule(rules.ParameterRule(parameter_expr))
        if owners:
            selector.add_rule(rules.OwnersRule(owners))
        if regex:
            selector.add_rule(rules.RegexRule(regex))
        specs = selector.run()
        self.db.put_selection(
            tag,
            signature,
            specs,
            scanpaths=scanpaths,
            on_options=on_options,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        logger.info(f"Created selection '[bold]{tag}[/]'")
        return specs

    def apply_selection_rules(
        self,
        specs: list["ResolvedSpec"],
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
    ) -> None:
        selector = select.Selector(specs, self.root)
        if keyword_exprs:
            selector.add_rule(rules.KeywordRule(keyword_exprs))
        if parameter_expr:
            selector.add_rule(rules.ParameterRule(parameter_expr))
        if owners:
            selector.add_rule(rules.OwnersRule(owners))
        if regex:
            selector.add_rule(rules.RegexRule(regex))
        if ids:
            selector.add_rule(rules.IDsRule(ids))
        if selector.rules:
            selector.run()

    def refresh_selection(self, tag: str) -> list["ResolvedSpec"]:
        selection = self.db.get_selection_metadata(tag)
        return self.create_selection(
            tag=tag,
            scanpaths=selection.scanpaths,
            on_options=selection.on_options,
            keyword_exprs=selection.keyword_exprs,
            parameter_expr=selection.parameter_expr,
            owners=selection.owners,
            regex=selection.regex,
        )

    def load_testcases(self, ids: list[str] | None = None) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed."""
        lookup: dict[str, TestCase] = {}
        latest = self.db.get_results(ids, include_upstreams=True)
        specs = self.db.get_specs(ids, include_upstreams=True)
        for spec in static_order(specs):
            if mine := latest.get(spec.id):
                dependencies = [lookup[dep.id] for dep in spec.dependencies]
                space = ExecutionSpace(
                    root=self.sessions_dir / mine["session"],
                    path=Path(mine["workspace"]),
                    session=mine["session"],
                )
                case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
                case.status = mine["status"]
                case.timekeeper = mine["timekeeper"]
                case.measurements = mine["measurements"]
                lookup[spec.id] = case
        if ids:
            return [case for case in lookup.values() if case.id in ids]
        return list(lookup.values())

    def select_from_view(
        self,
        path: Path,
    ) -> list["ResolvedSpec"]:
        ids: list[str] = []
        for file in path.rglob("*/testcase.lock"):
            lock_data = json.loads(file.read_text())
            ids.append(lock_data["spec"]["id"])
        resolved = self.db.get_specs(ids=ids)
        return resolved

    def remove_tag(self, tag: str) -> bool:
        if not self.db.is_selection(tag):
            logger.error(f"{tag!r} is not a tag")
            return False
        self.db.delete_selection(tag)
        return True

    def is_tag(self, tag: str) -> bool:
        return self.db.is_selection(tag)

    def generate_testspecs(
        self,
        generators: list["AbstractTestGenerator"],
        on_options: list[str] | None = None,
    ) -> tuple[str, list[ResolvedSpec]]:
        """Generate resolved test specs

        Args:
          on_options: Used to filter tests by option.  In the typical case, options are added to
            ``on_options`` by passing them on the command line, e.g., ``-o dbg`` would add ``dbg`` to
            ``on_options``.  Tests can define filtering criteria based on what options are on.

        Returns:
          Resolved specs

        """
        # canary selection create -r examples -k foo-bar foo-bar
        # canary selection create -r examples -k baz baz
        # canary selection refresh baz
        on_options = on_options or []
        generator = Generator(generators, workspace=self.root, on_options=on_options or [])
        if cached := self.db.get_specs_by_signature(generator.signature):
            logger.info("[bold]Retrieved[/] %d test specs from cache" % len(cached))
            return generator.signature, cached
        resolved = generator.run()
        pm = logger.progress_monitor("[bold]Caching[/] test specs")
        self.db.put_specs(generator.signature, resolved)
        pm.done()
        return generator.signature, resolved

    def construct_testcases(self, specs: list["ResolvedSpec"], session: Path) -> list["TestCase"]:
        lookup: dict[str, TestCase] = {}
        cases: list[TestCase] = []
        latest = self.db.get_results([spec.id for spec in specs])
        for spec in static_order(specs):
            dependencies = [lookup[dep.id] for dep in spec.dependencies]
            case: TestCase
            if spec.id in latest:
                # This case won't run, but it may be needed by dependents
                mine = latest[spec.id]
                space = ExecutionSpace(
                    root=self.sessions_dir / mine["session"],
                    path=Path(mine["workspace"]),
                    session=mine["session"],
                )
                case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
                case.status = mine["status"]
                case.timekeeper = mine["timekeeper"]
                case.measurements = mine["measurements"]
            else:
                space = ExecutionSpace(root=session, path=Path(spec.execpath), session=session.name)
                case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
            lookup[spec.id] = case
            cases.append(case)
        return cases

    def get_selection(self, tag: str | None) -> list["ResolvedSpec"]:
        if tag is None or tag == ":all:":
            return self.db.get_specs()
        return self.db.get_specs_by_tagname(tag)

    def gc(self, dryrun: bool = False) -> None:
        """Keep only the latet results"""
        raise NotImplementedError

        def mtime(path: Path):
            return path.stat().st_mtime

        logger.info(f"Garbage collecting {self.root}")
        latest: dict[str, TestCase] = {}
        view: dict[str, tuple[str, str]] = {}
        to_remove: list[TestCase] = []
        for session in self.sessions():
            for case in session.cases:
                if case.id not in latest:
                    latest[case.id] = case
                elif mtime(latest[case.id].workspace.dir) > mtime(case.workspace.dir):
                    to_remove.append(latest[case.id])
                    latest[case.id] = case
                else:
                    continue
                ws_dir = latest[case.id].workspace.dir
                relpath = ws_dir.relative_to(session.work_dir)
                view[case.id] = (str(session.work_dir), str(relpath))
        try:
            for case in to_remove:
                logger.info(f"gc: removing {case}::{case.workspace.dir}")
                if not dryrun:
                    case.workspace.remove()
        finally:
            logger.info(f"Garbage collected {len(to_remove)} test cases")
            if not dryrun:
                view_entries: dict[Path, list[Path]] = {}
                for root, path in view.values():
                    view_entries.setdefault(Path(root), []).append(Path(path))
                self.update_view(view_entries)

    def find(self, *, case: str | None = None, spec: str | None = None) -> Any:
        """Locate something in the workspace"""
        assert not (case and spec)
        if case is not None:
            return self.find_testcase(case)
        if spec is not None:
            return self.find_testspec(spec)

    def find_testcase(self, root: str) -> TestCase:
        id = self.db.resolve_spec_id(root)
        if id is not None:
            try:
                return self.load_testcases([id])[0]
            except IndexError:
                raise ValueError(f"{id}: no matching test case found in {self.root}")
        # Do the full (slow) lookup
        cases = self.load_testcases()
        for case in cases:
            if case.spec.matches(root):
                return case
        raise ValueError(f"{root}: no matching test case found in {self.root}")

    def find_testspec(self, root: str) -> ResolvedSpec:
        id = self.db.resolve_spec_id(root)
        if id is not None:
            try:
                return self.db.get_specs([id])[0]
            except IndexError:
                raise ValueError(f"{id}: no matching spec found in {self.root}")
        # Do the full (slow) lookup
        specs = self.db.get_specs()
        for spec in specs:
            if spec.matches(root):
                return spec
        raise ValueError(f"{root}: no matching spec found in {self.root}")

    def compute_rerun_closure(
        self, predicate: Callable[[str, dict], bool]
    ) -> tuple[list["ResolvedSpec"], list["ResolvedSpec"]]:
        results = self.db.get_results()
        selected: set[str] = set()
        for id, result in results.items():
            if predicate(id, result):
                selected.add(id)
        upstream, downstream = self.db.get_updownstream_ids(list(selected))
        run_specs = selected | downstream
        get_specs = run_specs | upstream
        resolved = self.db.get_specs(ids=list(get_specs))
        return stable_partition(resolved, predicate=lambda spec: spec.id not in run_specs)

    def compute_failed_rerun_list(self) -> tuple[list["ResolvedSpec"], list["ResolvedSpec"]]:
        def predicate(id: str, result: dict) -> bool:
            if result["status"]["category"] in ("FAILED", "ERROR", "BROKEN", "DIFFED", "BLOCKED"):
                return True
            return False

        return self.compute_rerun_closure(predicate)

    def compute_rerun_list_for_specs(
        self, ids: list[str]
    ) -> tuple[list["ResolvedSpec"], list["ResolvedSpec"]]:
        def predicate(id: str, result: dict) -> bool:
            return id in ids

        self.db.resolve_spec_ids(ids)
        return self.compute_rerun_closure(predicate)

    def load_testspecs(self, ids: list[str] | None = None) -> list["ResolvedSpec"]:
        return self.db.get_specs(ids)

    def find_specids(self, ids: list[str]) -> list[str | None]:
        specs = self.db.get_specs()
        found: list[str | None] = []
        for id in ids:
            if id.startswith(testspec.select_sygil):
                id = id[1:]
            for spec in specs:
                if spec.id.startswith(id):
                    found.append(spec.id)
                    break
                elif id in (spec.name, spec.display_name(), spec.display_name(resolve=True)):
                    found.append(spec.id)
                    break
                elif fnmatch.fnmatch(id, spec.name):
                    found.append(spec.id)
                    break
            else:
                found.append(None)
        return found


def find_generators_in_path(path: str | Path) -> list[AbstractTestGenerator]:
    collector = Collector()
    collector.add_scanpath(str(path), [])
    generators = collector.run()
    return generators


class WorkspaceDatabase:
    """Database wrapper"""

    connection: sqlite3.Connection

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self.connection.execute("PRAGMA synchronous=NORMAL;")
        self.connection.execute("PRAGMA foreign_key=ON;")

    @classmethod
    def create(cls, path: Path) -> "WorkspaceDatabase":
        self = cls(path)
        with self.connection:
            query = """CREATE TABLE IF NOT EXISTS specs (
              spec_id TEXT PRIMARY KEY,
              signature TEXT NOT NULL,
              file TEXT NOT NULL,
              data BLOB NOT NULL
            )"""
            self.connection.execute(query)

            query = """CREATE TABLE IF NOT EXISTS spec_deps (
              spec_id TEXT NOT NULL,
              dep_id TEXT NOT NULL,
              PRIMARY KEY (spec_id, dep_id),
              FOREIGN KEY (spec_id) REFERENCES specs(spec_id) ON DELETE CASCADE
              FOREIGN KEY (dep_id)  REFERENCES specs(spec_id)
            )"""
            self.connection.execute(query)

            query = "CREATE INDEX IF NOT EXISTS ix_spec_deps_spec_id ON spec_deps (spec_id)"
            self.connection.execute(query)

            query = "CREATE INDEX IF NOT EXISTS ix_spec_deps_dep_id ON spec_deps (dep_id)"
            self.connection.execute(query)

            query = """CREATE TABLE IF NOT EXISTS selections (
              id TEXT PRIMARY KEY,
              tag TEXT UNIQUE,
              gen_signature TEXT,
              created_on TEXT,
              canary_version TEXT,
              scanpaths TEXT,
              on_options TEXT,
              keyword_exprs TEXT,
              parameter_expr TEXT,
              owners TEXT,
              regex TEXT,
              fingerprint TEXT
            )
            """
            self.connection.execute(query)

            query = """CREATE TABLE IF NOT EXISTS selection_specs (
              selection_id TEXT,
              spec_id TEXT,
              PRIMARY KEY (selection_id, spec_id),
              FOREIGN KEY (selection_id) REFERENCES selections(spec_id) ON DELETE CASCADE
            )"""
            self.connection.execute(query)

            query = """CREATE TABLE IF NOT EXISTS results (
            spec_id TEXT,
            spec_name TEXT,
            spec_fullname TEXT,
            file_root TEXT,
            file_path TEXT,
            session TEXT,
            status_state TEXT,
            status_category TEXT,
            status_status TEXT,
            status_reason TEXT,
            status_code INTEGER,
            started_on TEXT,
            finished_on TEXT,
            duration TEXT,
            workspace TEXT,
            measurements TEXT,
            PRIMARY KEY (spec_id, session)
            )"""
            self.connection.execute(query)

            query = "CREATE INDEX IF NOT EXISTS ix_results_id ON results (spec_id)"
            self.connection.execute(query)

            query = "CREATE INDEX IF NOT EXISTS ix_results_session ON results (session)"
            self.connection.execute(query)

        return self

    @classmethod
    def load(cls, path: Path) -> "WorkspaceDatabase":
        self = cls(path)
        return self

    def close(self):
        self.connection.close()

    def put_specs(self, signature: str, specs: list[ResolvedSpec]) -> None:
        spec_rows: list[tuple[str, str, str, bytes]] = []
        dep_rows: list[tuple[str, str]] = []
        for spec in specs:
            try:
                deps = spec.dependencies
                spec.dependencies = []
                blob = pickle.dumps(spec, protocol=pickle.HIGHEST_PROTOCOL)
            finally:
                spec.dependencies = deps
            spec_rows.append((spec.id, signature, str(spec.file), blob))
            for dep in spec.dependencies:
                dep_rows.append((spec.id, dep.id))
        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _spec_ids(id TEXT PRIMARY KEY)")
            self.connection.executemany(
                "INSERT INTO _spec_ids(id) VALUES (?)",
                ((spec.id,) for spec in specs),
            )
            # 2. Bulk insert/update specs
            self.connection.executemany(
                """
                  INSERT INTO specs (spec_id, signature, file, data)
                  VALUES (?, ?, ?, ?)
                  ON CONFLICT(spec_id) DO UPDATE SET signature=excluded.signature, data=excluded.data
                  """,
                spec_rows,
            )

            # 3. Bulk delete old dependencies for these specs
            self.connection.execute(
                "DELETE FROM spec_deps WHERE spec_id IN (SELECT id FROM _spec_ids)"
            )

            # 4. Bulk insert new dependencies using generator (minimal memory)
            self.connection.executemany(
                "INSERT INTO spec_deps(spec_id, dep_id) VALUES (?, ?)", dep_rows
            )

            # 5. Drop temporary table
            self.connection.execute("DROP TABLE _spec_ids")

    def resolve_spec_id(self, id: str) -> str | None:
        if id.startswith(testspec.select_sygil):
            id = id[1:]
        try:
            hi = increment_hex_prefix(id)
        except ValueError:
            return None
        if hi is None:
            return None
        rows = self.connection.execute(
            "SELECT spec_id FROM specs WHERE spec_id >= ? AND spec_id < ? LIMIT 2", (id, hi)
        ).fetchall()
        if len(rows) == 0:
            return None
        elif len(rows) > 1:
            raise ValueError(f"Ambiguous spec ID {id!r}")
        return rows[0][0]

    def resolve_spec_ids(self, ids: list[str]):
        """Given partial spec IDs in ``ids``, expand them to their full size"""
        for i, id in enumerate(ids):
            if id.startswith(testspec.select_sygil):
                id = id[1:]
            if len(id) >= 64:
                continue
            hi = increment_hex_prefix(id)
            assert hi is not None
            cur = self.connection.execute(
                """
                SELECT spec_id
                FROM specs
                WHERE spec_id >= ? AND spec_id < ?
                ORDER BY spec_id LIMIT 2
                """,
                (id, hi),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"No match for spec ID {id!r}")
            if cur.fetchone():
                raise ValueError(f"Ambiguous spec ID {id!r}")
            ids[i] = row[0]

    def get_specs(
        self, ids: list[str] | None = None, include_upstreams: bool = False
    ) -> list[ResolvedSpec]:
        rows: list[tuple[str, str, str, bytes]]
        if not ids:
            rows = self.connection.execute("SELECT * FROM specs").fetchall()
            return self._reconstruct_specs(rows)
        self.resolve_spec_ids(ids)
        upstream = self.get_upstream_ids(ids)
        load_ids = list(upstream.union(ids))
        rows = []
        base_query = "SELECT * FROM specs WHERE spec_id IN"
        for i in range(0, len(load_ids), SQL_CHUNK_SIZE):
            chunk = load_ids[i : i + SQL_CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            query = f"{base_query} ({placeholders})"
            cursor = self.connection.execute(query, chunk)
            rows.extend(cursor.fetchall())
        specs = self._reconstruct_specs(rows)
        if include_upstreams:
            return specs
        return [spec for spec in specs if spec.id in ids]

    def get_specs_by_signature(self, signature: str) -> list[ResolvedSpec]:
        rows = self.connection.execute(
            "SELECT * FROM specs WHERE signature = ?", (signature,)
        ).fetchall()
        return self._reconstruct_specs(rows)

    def get_specs_by_tagname(self, tag: str) -> list["ResolvedSpec"]:
        rows = self.connection.execute(
            """
            SELECT ss.spec_id
            FROM selections s
            JOIN selection_specs ss
            ON ss.selection_id = s.id
            WHERE s.tag = ?
            """,
            (tag,),
        ).fetchall()
        if not rows:
            raise NotASelection(tag)
        return self.get_specs([r[0] for r in rows])

    def _reconstruct_specs(self, rows: list[tuple[str, str, str, bytes]]) -> list[ResolvedSpec]:
        specs: dict[str, ResolvedSpec] = {}
        for row in rows:
            spec = pickle.loads(row[-1])  # nosec B301
            spec.dependencies = []
            specs[spec.id] = spec
        ids = [spec.id for spec in specs.values()]
        edges = self.get_edges(ids)
        for spec_id, dep_id in edges:
            specs[spec_id].dependencies.append(specs[dep_id])
        return list(specs.values())

    def get_edges(self, ids: list[str] | None = None) -> list[tuple[str, str]]:
        if not ids:
            return self.connection.execute("SELECT spec_id, dep_id FROM spec_deps").fetchall()
        rows: list[tuple[str, str]] = []
        base_query = "SELECT spec_id, dep_id FROM spec_deps WHERE spec_id IN"
        for i in range(0, len(ids), SQL_CHUNK_SIZE):
            chunk = ids[i : i + SQL_CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            query = f"{base_query} ({placeholders})"
            cursor = self.connection.execute(query, chunk)
            rows.extend(cursor.fetchall())
        return rows

    def put_results(self, session: Session) -> None:
        """Store results in the DB.  We store status, timekeeper across columns for future
        enhancements to use results without actually creating a testcase to hold them
        """
        rows = []
        for case in session.cases:
            rows.append(
                (
                    case.id,
                    case.spec.name,
                    case.spec.fullname,
                    str(case.spec.file_root),
                    str(case.spec.file_path),
                    session.name,
                    case.status.state,
                    case.status.category,
                    case.status.status,
                    case.status.reason or "",
                    case.status.code,
                    case.timekeeper.started_on,
                    case.timekeeper.finished_on,
                    case.timekeeper.duration,
                    str(case.workspace.path),
                    json.dumps_min(case.measurements.asdict()),
                )
            )
        with self.connection:
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO results (
                spec_id,
                spec_name,
                spec_fullname,
                file_root,
                file_path,
                session,
                status_state,
                status_category,
                status_status,
                status_reason,
                status_code,
                started_on,
                finished_on,
                duration,
                workspace,
                measurements
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_results(
        self,
        ids: list[str] | None = None,
        include_upstreams: bool = False,
    ) -> dict[str, dict[str, Any]]:
        rows: list[tuple[str, ...]]
        if not ids:
            rows = self.connection.execute(
                """SELECT *
                FROM results AS r
                WHERE r.session = (
                  SELECT MAX(session)
                  FROM results AS r2
                  WHERE r2.spec_id = r.spec_id
                )
                """
            ).fetchall()
            return {row[0]: self._reconstruct_results(row) for row in rows}
        rows = []
        self.resolve_spec_ids(ids)
        upstream = self.get_upstream_ids(ids) if include_upstreams else set()
        load_ids = list(upstream.union(ids))
        for i in range(0, len(load_ids), SQL_CHUNK_SIZE):
            chunk = load_ids[i : i + SQL_CHUNK_SIZE]
            placeholders = ", ".join("?" for _ in chunk)
            query = f"""\
              SELECT r.*
                FROM results AS r
                WHERE r.spec_id in ({placeholders})
                AND r.session = (
                  SELECT MAX(session)
                  FROM results AS r2
                  WHERE r2.spec_id = r.spec_id
                )
            """  # nosec B608
            cur = self.connection.execute(query, chunk)  # nosec B608
            rows.extend(cur.fetchall())
        return {row[0]: self._reconstruct_results(row) for row in rows}

    def get_result_history(self, id: str) -> list:
        rows = self.connection.execute(
            "SELECT * FROM results WHERE spec_id LIKE ? ORDER BY session ASC", (f"{id}%",)
        ).fetchall()
        data: list[dict] = []
        for row in rows:
            d = self._reconstruct_results(row)
            data.append(d)
        return data

    def _reconstruct_results(self, row: tuple[str, ...]) -> dict[str, Any]:
        d: dict[str, Any] = {}
        d["id"] = row[0]
        d["spec_name"] = row[1]
        d["spec_fullname"] = row[2]
        d["file_root"] = row[3]
        d["file_path"] = row[4]
        d["session"] = row[5]
        d["status"] = Status.from_dict(
            {
                "state": row[6],
                "category": row[7],
                "status": row[8],
                "reason": row[9],
                "code": row[10],
            }
        )
        d["timekeeper"] = Timekeeper.from_dict(
            {
                "started_on": row[11],
                "finished_on": row[12],
                "duration": float(row[13]),
            }
        )
        d["workspace"] = row[14]
        d["measurements"] = Measurements.from_dict(json.loads(row[15]))
        return d

    def put_selection(
        self,
        tag: str,
        signature: str,
        specs: list["ResolvedSpec"],
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> None:
        if tag == ":all:":
            raise ValueError("Tag name :all: is reserved")
        row: list[str] = []
        id = uuid.uuid4().hex
        row.extend((id, tag, signature, datetime.datetime.now().isoformat(), __static_version__))

        hasher = hashlib.sha256()
        row.append(json.dumps_min(scanpaths, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(on_options, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(keyword_exprs, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(parameter_expr))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(owners, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(regex))
        hasher.update(row[-1].encode())

        fingerprint = hasher.hexdigest()
        row.append(fingerprint)

        with self.connection:
            self.connection.execute("DELETE FROM selections WHERE tag = ?", (tag,))
            self.connection.executemany(
                """
                INSERT INTO selection_specs (selection_id, spec_id)
                VALUES (?, ?)
                """,
                ((id, spec.id) for spec in specs),
            )
            self.connection.execute(
                """
                INSERT INTO selections (
                  id,
                  tag,
                  gen_signature,
                  created_on,
                  canary_version,
                  scanpaths,
                  on_options,
                  keyword_exprs,
                  parameter_expr,
                  owners,
                  regex,
                  fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    def rename_selection(self, old: str, new: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE selections SET tag = ? WHERE tag = ?", (new, old))

    def get_selection_metadata(self, tag: str) -> "Selection":
        row = self.connection.execute("SELECT * FROM selections WHERE tag = ?", (tag,)).fetchone()
        if not row:
            raise NotASelection(tag)
        return Selection(
            id=row[0],
            tag=row[1],
            gen_signature=row[2],
            created_on=datetime.datetime.fromisoformat(row[3]),
            canary_version=row[4],
            scanpaths=json.loads(row[5]),
            on_options=json.loads(row[6]),
            keyword_exprs=json.loads(row[7]),
            parameter_expr=json.loads(row[8]),
            owners=json.loads(row[9]),
            regex=json.loads(row[10]),
            fingerprint=row[11],
        )

    @property
    def tags(self) -> list[str]:
        rows = self.connection.execute("SELECT tag FROM selections").fetchall()
        return [row[0] for row in rows]

    def is_selection(self, tag: str) -> bool:
        cur = self.connection.execute("SELECT 1 FROM selections WHERE tag = ? LIMIT 1", (tag,))
        return cur.fetchone() is not None

    def delete_selection(self, tag: str) -> bool:
        with self.connection:
            self.connection.execute("DELETE FROM selections WHERE tag = ?", (tag,))
        return True

    def get_updownstream_ids(self, seeds: Iterable[str] | None = None) -> tuple[set[str], set[str]]:
        if seeds is None:
            return set(), set()
        downstream = self.get_downstream_ids(seeds)
        upstream = self.get_upstream_ids(downstream.union(seeds))
        return upstream, downstream

    def get_downstream_ids(self, seeds: Iterable[str]) -> set[str]:
        """Return dependencies in instantiation order."""
        if not seeds:
            return set()
        values = ",".join("(?)" for _ in seeds)
        query = f"""
        WITH RECURSIVE
        seeds(id) AS (VALUES {values}),
        downstream(id) AS (
          SELECT spec_id
          FROM spec_deps
          WHERE dep_id IN (SELECT id FROM seeds)
          UNION
          SELECT d.spec_id
          FROM spec_deps d
          JOIN downstream dn ON d.dep_id = dn.id
        )
        SELECT DISTINCT id FROM downstream
        """  #  nosec B608
        rows = self.connection.execute(query, tuple(seeds)).fetchall()
        return {r[0] for r in rows}

    def get_upstream_ids(self, seeds: Iterable[str]) -> set[str]:
        """Return dependents in reverse instantiation order."""
        if not seeds:
            return set()
        values = ",".join("(?)" for _ in seeds)
        query = f"""
        WITH RECURSIVE
        seeds(id) AS (VALUES {values}),
        upstream(id) AS (
          SELECT dep_id
          FROM spec_deps
          WHERE spec_id IN (SELECT id FROM seeds)
          UNION
          SELECT d.dep_id
          FROM spec_deps d
          JOIN upstream u ON d.spec_id = u.id
        )
        SELECT DISTINCT id FROM upstream
        """  # nosec B608
        rows = self.connection.execute(query, tuple(seeds)).fetchall()
        return {r[0] for r in rows}

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """
        Return the entire dependency graph, including disconnected nodes.
        Every spec appears, standalone nodes have dep_id=None (empty list).
        """
        graph: dict[str, list[str]] = collections.defaultdict(list)
        rows = self.connection.execute("SELECT spec_id FROM specs").fetchall()
        for (spec_id,) in rows:
            graph[spec_id] = []
        rows = self.connection.execute("SELECT spec_id, dep_id FROM spec_deps").fetchall()
        for spec_id, dep_id in rows:
            graph[spec_id].append(dep_id)
        return graph


T = TypeVar("T")


def stable_partition(seq: Sequence[T], predicate: Callable[[T], bool]) -> tuple[list[T], list[T]]:
    true: list[T] = []
    false: list[T] = []
    for item in seq:
        if predicate(item):
            true.append(item)
        else:
            false.append(item)
    return true, false


def increment_hex_prefix(prefix: str) -> str | None:
    try:
        value = int(prefix, 16)
    except ValueError:
        raise ValueError(f"Ivalid hex prefix: {prefix!r}") from None
    max_value = (1 << (4 * len(prefix))) - 1
    if value == max_value:
        logger.warning("No valid upper bound - prefix overflow")
        return None
    return f"{value + 1:0{len(prefix)}x}"


@dataclasses.dataclass
class Selection:
    id: str
    tag: str
    gen_signature: str
    created_on: datetime.datetime
    canary_version: str
    scanpaths: dict[str, list[str]]
    on_options: list[str] | None
    keyword_exprs: list[str] | None
    parameter_expr: str | None
    owners: list[str] | None
    regex: str | None
    fingerprint: str


class WorkspaceExistsError(Exception):
    pass


class NotAWorkspaceError(Exception):
    pass


class SpecNotFoundError(Exception):
    pass


class NotASelection(Exception):
    def __init__(self, tag):
        super().__init__(f"No selection for tag {tag!r} found")
