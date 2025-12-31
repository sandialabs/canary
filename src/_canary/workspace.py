# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import fnmatch
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from . import config
from . import rules
from . import select
from . import testspec
from .collect import Collector
from .database import WorkspaceDatabase
from .error import StopExecution
from .error import notests_exit_status
from .generate import Generator
from .generator import AbstractTestGenerator
from .runtest import Runner
from .runtest import canary_runtests
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import ResolvedSpec
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
        config.ensure_loaded()
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

    def relative_to_view(self, path: str | os.PathLike[str]) -> str | None:
        """
        If `path` is inside TestResults, return the relative path (which
        may include glob characters). Otherwise return None.

        Examples:
          /ws/TestResults/foo/bar/test.py  -> foo/bar/test.py
        """
        if self.view is None:
            return None
        p = Path(path).absolute()
        if p.is_relative_to(self.view):
            return str(p.relative_to(self.view))
        return None

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
        specs = self.db.load_specs(ids, include_upstreams=True)
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
        resolved = self.db.load_specs(ids=ids)
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
        if cached := self.db.load_specs_by_signature(generator.signature):
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
            return self.db.load_specs()
        return self.db.load_specs_by_tagname(tag)

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
                return self.db.load_specs([id])[0]
            except IndexError:
                raise ValueError(f"{id}: no matching spec found in {self.root}")
        # Do the full (slow) lookup
        specs = self.db.load_specs()
        for spec in specs:
            if spec.matches(root):
                return spec
        raise ValueError(f"{root}: no matching spec found in {self.root}")

    def find_specids(self, ids: list[str]) -> list[str | None]:
        specs = self.db.load_specs()
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


class WorkspaceExistsError(Exception):
    pass


class NotAWorkspaceError(Exception):
    pass


class SpecNotFoundError(Exception):
    pass
