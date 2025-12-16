# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import fnmatch
import os
import shutil
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any
from typing import Callable
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
from .testspec import Mask
from .testspec import ResolvedSpec
from .timekeeper import Timekeeper
from .util import json_helper as json
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import write_directory_tag
from .util.graph import TopologicalSorter
from .util.graph import reachable_nodes
from .util.graph import reachable_up_down
from .util.graph import static_order

logger = logging.get_logger(__name__)

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
view_tag = "VIEW.TAG"


DB_MAX_RETRIES = 8
DB_BASE_DELAY = 0.05  # 50ms base for exponential backoff (0.05, 0.1, 0.2, ...)


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

        if var := config.get("view"):
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
        file = self.root / "canary.yaml"
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
        for case in self.load_testcases():
            if not case.workspace.session:
                continue
            relpath = case.workspace.dir.relative_to(self.sessions_dir / case.workspace.session)
            view[case.id] = (str(self.sessions_dir / case.workspace.session), str(relpath))
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
        import canary

        latest_session: str | None = None
        if (self.refs_dir / "latest").exists():
            link = (self.refs_dir / "latest").read_text().strip()
            path = self.refs_dir / link
            latest_session = path.stem
        generator_count = self.db.count("generators")
        info = {
            "root": str(self.root),
            "generator_count": generator_count,
            "session_count": len([p for p in self.sessions_dir.glob("*") if p.is_dir()]),
            "latest_session": latest_session,
            "tags": self.db.tags,
            "version": canary.version,
            "workspace_version": (self.root / "VERSION").read_text().strip(),
        }
        return info

    def load_generators(self) -> list[AbstractTestGenerator]:
        """Load test case generators"""
        pm = logger.progress_monitor("[bold]Loading[/bold] test case generators from cache")
        generators = self.db.get_generators()
        pm.done()
        return generators

    def active_testcases(self) -> list[TestCase]:
        return self.load_testcases()

    def find_and_add_generators(
        self, scanpaths: dict[str, list[str]], pedantic: bool = True
    ) -> list[AbstractTestGenerator]:
        """Find test case generators in scan_paths and add them to this workspace"""
        collector = Collector()
        collector.add_scanpaths(scanpaths)
        generators = collector.run()
        self.db.put_generators(generators)
        logger.info(f"[bold]Added[/] {len(generators)} new test case generators to {self.root}")
        return generators

    def load_testcases(self, ids: list[str] | None = None) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed."""
        lookup: dict[str, TestCase] = {}
        reachable: list[str] | None = None
        if ids:
            reachable = self.db.reachable_spec_ids(ids)
        latest = self.db.get_results(ids=reachable)
        specs = self.db.get_specs(ids=reachable)
        for spec in static_order(specs):
            if mine := latest.get(spec.id):
                dependencies = [lookup[dep.id] for dep in spec.dependencies]
                space = ExecutionSpace(
                    root=self.root / "sessions" / mine["session"],
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
        if tag == "default":
            logger.error("Cannot remove default tag")
            return False
        if not self.db.is_selection(tag):
            logger.error(f"{tag!r} is not a tag")
            return False
        self.db.delete_selection(tag)
        return True

    def is_tag(self, tag: str) -> bool:
        return self.db.is_selection(tag)

    def generate_testspecs(self, on_options: list[str] | None = None) -> list[ResolvedSpec]:
        """Generate resolved test specs

        Args:
          on_options: Used to filter tests by option.  In the typical case, options are added to
            ``on_options`` by passing them on the command line, e.g., ``-o dbg`` would add ``dbg`` to
            ``on_options``.  Tests can define filtering criteria based on what options are on.

        Returns:
          Resolved specs

        """
        on_options = on_options or []
        generators = self.load_generators()
        generator = Generator(generators, workspace=self.root, on_options=on_options or [])
        if cached := self.db.get_specs(signature=generator.signature):
            logger.info("[bold]Retrieved[/] %d test specs from cache" % len(cached))
            return cached
        resolved = generator.run()
        pm = logger.progress_monitor("[bold]Caching[/] test specs")
        self.db.put_specs(generator.signature, resolved)
        pm.done()
        return resolved

    def construct_testcases(self, specs: list["ResolvedSpec"], session: Path) -> list["TestCase"]:
        lookup: dict[str, TestCase] = {}
        cases: list[TestCase] = []
        latest = self.db.get_results()
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

    def make_selection(
        self,
        tag: str | None = None,
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
        generate: bool | None = None,
    ) -> list["ResolvedSpec"]:
        """Select final test specs

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
          owners: Used to filter tests by owner.

        Returns:
          Test spec selection

        """
        resolved = self.load_testspecs()
        if not resolved and generate in (True, None):
            resolved = self.generate_testspecs()
        if not resolved:
            raise StopExecution(
                "There are no test specs in this workspace, did you run `canary generate`?",
                exit_code=notests_exit_status,
            )
        self.apply_selection_rules(
            resolved,
            tag=tag,
            prefixes=prefixes,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            ids=ids,
        )
        return resolved

    def apply_selection_rules(
        self,
        specs: list["ResolvedSpec"],
        tag: str | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
        prefixes: list[str] | None = None,
    ) -> None:
        selector = select.Selector(specs, self.root)
        if ids:
            selector.add_rule(rules.IDsRule(ids))
        if keyword_exprs:
            selector.add_rule(rules.KeywordRule(keyword_exprs))
        if prefixes:
            selector.add_rule(rules.PrefixRule(prefixes))
        if parameter_expr:
            selector.add_rule(rules.ParameterRule(parameter_expr))
        if owners:
            selector.add_rule(rules.OwnersRule(owners))
        if regex:
            selector.add_rule(rules.RegexRule(regex))
        if tag is None and len(selector.rules) == 0:
            # Default: 1 rule for resource availability
            tag = "default"
        selector.run()
        if tag:
            self.db.put_selection(tag, selector.snapshot())

    def get_selector(self, tag: str = "default"):
        if tag == "default" and not self.db.is_selection(tag):
            return select.SelectorSnapshot("", dict(), [], "")
        return self.db.get_selection(tag)

    def get_selection(self, tag: str = "default") -> list["ResolvedSpec"]:
        if tag == "default" and not self.db.is_selection(tag):
            return self.make_selection(tag="default")
        snapshot = self.db.get_selection(tag)
        resolved = self.db.get_specs()
        if snapshot.is_compatible_with_specs(resolved):
            snapshot.apply(resolved)
            return resolved
        else:
            selector = select.Selector.from_snapshot(resolved, self.root, snapshot)
            selector.run()
            self.db.put_selection(tag, selector.snapshot())
            return selector.specs

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

    def compute_rerun_list(
        self, predicate: Callable[[str, dict], bool]
    ) -> tuple[list["ResolvedSpec"], list["ResolvedSpec"]]:
        results = self.db.get_results()
        selected: set[str] = set()
        for id, result in results.items():
            if predicate(id, result):
                selected.add(id)
        graph = self.db.get_dependency_graph()
        upstream, downstream = reachable_up_down(graph, selected)
        run_specs = selected | downstream
        load_specs = run_specs | upstream
        resolved = self.db.get_specs(ids=list(load_specs))
        return stable_partition(resolved, predicate=lambda spec: spec.id not in run_specs)

    def compute_failed_rerun_list(self) -> tuple[list["ResolvedSpec"], list["ResolvedSpec"]]:
        def predicate(id: str, result: dict) -> bool:
            if result["status"]["category"] in ("FAILED", "ERROR", "BROKEN", "DIFFED", "BLOCKED"):
                return True
            return False

        return self.compute_rerun_list(predicate)

    def compute_rerun_list_for_specs(
        self, ids: list[str]
    ) -> tuple[list["ResolvedSpec"], list["ResolvedSpec"]]:
        def predicate(id: str, result: dict) -> bool:
            return id in ids

        self.db.resolve_spec_ids(ids)
        return self.compute_rerun_list(predicate)

    def load_testspecs(self, ids: list[str] | None = None) -> list["ResolvedSpec"]:
        if not ids:
            return self.db.get_specs()
        graph = self.db.get_dependency_graph()
        reachable = reachable_nodes(graph, ids)
        specs = self.db.get_specs(ids=reachable)
        for spec in specs:
            if spec.id not in ids:
                spec.mask = Mask.masked("ID not requested")
        return specs

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
    """Database wrapper for the "latest results" index."""

    connection: sqlite3.Connection
    tables = (
        "generators",
        "specs",
        "dependencies",
        "selections",
        "results",
    )

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self.connection.execute("PRAGMA synchronous=NORMAL;")
        self.connection.execute("PRAGMA foreign_key=ON;")

    @classmethod
    def create(cls, path: Path) -> "WorkspaceDatabase":
        """
        Create the 'LATEST' table if it doesn't exist.
        """
        self = cls(path)
        with self.connection:
            query = "CREATE TABLE IF NOT EXISTS generators (id TEXT PRIMARY KEY, data TEXT)"
            self.connection.execute(query)

            query = """CREATE TABLE IF NOT EXISTS specs (
            id TEXT PRIMARY KEY, signature TEXT, data TEXT
            )"""
            self.connection.execute(query)

            query = "CREATE TABLE IF NOT EXISTS dependencies (id TEXT PRIMARY KEY, data TEXT)"
            self.connection.execute(query)

            query = "CREATE TABLE IF NOT EXISTS selections (tag TEXT PRIMARY KEY, data TEXT)"
            self.connection.execute(query)

            query = """CREATE TABLE IF NOT EXISTS results (
            id TEXT,
            spec_name TEXT,
            spec_fullname TEXT,
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
            PRIMARY KEY (id, session)
            )"""
            self.connection.execute(query)

            query = "CREATE INDEX IF NOT EXISTS ix_results_id ON results (id)"
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

    def put_generators(self, generators: list[AbstractTestGenerator]) -> None:
        pm = logger.progress_monitor("[bold]Putting[/] test generators into database")
        with self.connection:
            rows = ((gen.id, gen.serialize()) for gen in generators)
            self.connection.executemany(
                """
                INSERT INTO generators (id, data)
                VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data
                """,
                rows,
            )
        pm.done()

    def count(self, table: str) -> int:
        if table not in self.tables:
            raise ValueError(f"{table} is not a valid table name")

        row = self.connection.execute(f"SELECT COUNT(*) FROM {table};").fetchone()  # nosec B608
        return int(row[0])

    def get_generators(self) -> list[AbstractTestGenerator]:
        rows = self.connection.execute("SELECT data FROM generators;").fetchall()
        with ProcessPoolExecutor() as ex:
            generators = list(ex.map(AbstractTestGenerator.reconstruct, [row[0] for row in rows]))
        return generators

    def put_specs(self, signature: str, specs: list[ResolvedSpec]) -> None:
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO specs (id, signature, data)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET signature=excluded.signature, data=excluded.data
                """,
                ((spec.id, signature, json.dumps_min(spec.asdict())) for spec in specs),
            )
            self.connection.executemany(
                """
                INSERT INTO dependencies (id, data)
                VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data
                """,
                (
                    (spec.id, json.dumps_min([dep.id for dep in spec.dependencies]))
                    for spec in specs
                ),
            )

    def reachable_spec_ids(self, ids: list[str]) -> list[str]:
        graph = self.get_dependency_graph()
        self.resolve_spec_ids(ids)
        return reachable_nodes(graph, ids)

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
            "SELECT id FROM specs WHERE id >= ? AND id < ? LIMIT 2", (id, hi)
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
                "SELECT id FROM specs WHERE id >= ? AND id < ? ORDER BY id LIMIT 2", (id, hi)
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"No match for spec ID {id!r}")
            if cur.fetchone():
                raise ValueError(f"Ambiguous spec ID {id!r}")
            ids[i] = row[0]

    def get_specs(
        self, ids: list[str] | None = None, signature: str | None = None
    ) -> list[ResolvedSpec]:
        if ids and signature:
            return self._get_specs_by_id_and_signature(ids, signature)
        elif ids:
            return self._get_specs_by_id(ids)
        elif signature:
            return self._get_specs_by_signature(signature)
        else:
            return self._get_all_specs()

    def _get_all_specs(self) -> list[ResolvedSpec]:
        rows = self.connection.execute("SELECT * FROM specs").fetchall()
        return self._reconstruct_specs(rows)

    def _get_specs_by_signature(self, signature: str) -> list[ResolvedSpec]:
        rows = self.connection.execute(
            "SELECT * FROM specs WHERE signature = ?", (signature,)
        ).fetchall()
        return self._reconstruct_specs(rows)

    def _get_specs_by_exact_id(self, exact: list[str]) -> list[Any]:
        rows = list()
        base_query = "SELECT * FROM specs WHERE id IN"
        if exact:
            while rem := len(exact) > 0:
                nvar = min(900, rem)
                placeholders = ",".join(["?"] * nvar)
                query = f"{base_query} ({placeholders})"
                cur = self.connection.execute(query, exact[:nvar])
                rows.extend(cur.fetchall())
                exact = exact[nvar:]
        return rows

    def _get_specs_by_partial_id(self, partial: list[str]) -> list[Any]:
        rows = list()
        base_query = "SELECT * FROM specs WHERE"
        if partial:
            while rem := len(partial) > 0:
                nvar = min(900, rem)
                clauses = " OR ".join(["id LIKE ?"] * nvar)
                params = [f"{p}%" for p in partial[:nvar]]
                query = f"{base_query} {clauses}"
                cur = self.connection.execute(query, params)
                rows.extend(cur.fetchall())
                partial = partial[nvar:]
        return rows

    def _get_specs_by_id(self, ids: list[str]) -> list[ResolvedSpec]:
        self.resolve_spec_ids(ids)
        graph = self.get_dependency_graph()
        reachable = reachable_nodes(graph, ids)
        exact, partial = stable_partition(reachable, predicate=lambda x: len(x) >= 64)
        rows = self._get_specs_by_exact_id(exact)
        rows.extend(self._get_specs_by_partial_id(partial))
        specs = self._reconstruct_specs(rows)
        return [spec for spec in specs if spec.id in ids]

    def _get_specs_by_id_and_signature(self, ids: list[str], signature: str) -> list[ResolvedSpec]:
        graph = self.get_dependency_graph()
        reachable = reachable_nodes(graph, ids)
        exact, partial = stable_partition(reachable, predicate=lambda x: len(x) >= 64)
        clauses: list[str] = []
        params: list[str] = []
        if exact:
            placeholders = ",".join(["?"] * len(exact))
            clauses.append(f"id IN ({placeholders})")
            params.extend(exact)
        for p in partial:
            clauses.append("id LIKE ?")
            params.append(f"{p}%")
        where = " OR ".join(clauses)
        query = f"SELECT * FROM specs WHERE signature = ? AND ({where})"  # nosec B608
        rows = self.connection.execute(query, (signature, *params)).fetchall()
        specs = self._reconstruct_specs(rows)
        return [spec for spec in specs if spec.id in ids]

    def _reconstruct_specs(self, rows: list[list]) -> list[ResolvedSpec]:
        data = {id: json.loads(data) for id, _, data in rows}
        graph = {id: [_["id"] for _ in s["dependencies"]] for id, s in data.items()}
        lookup: dict[str, ResolvedSpec] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            spec = ResolvedSpec.from_dict(data[id], lookup)
            lookup[id] = spec
        return list(lookup.values())

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
                id,
                spec_name,
                spec_fullname,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_results(self, ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        if not ids:
            rows = self.connection.execute(
                """SELECT *
                FROM results AS r
                WHERE r.session = (SELECT MAX(session) FROM results AS r2 WHERE r2.id = r.id)
                """
            ).fetchall()
        else:
            rows = []
            batch_size = 900
            self.resolve_spec_ids(ids)
            for i in range(0, len(ids), batch_size):
                batch = ids[i : i + batch_size]
                placeholders = ", ".join("?" * len(batch))
                query = f"""\
                  SELECT r.*
                    FROM results AS r
                    WHERE r.id in ({placeholders})
                    AND r.session = (SELECT MAX(session) FROM results AS r2 WHERE r2.id = r.id)
                """  # nosec B608
                cur = self.connection.execute(query, batch)  # nosec B608
                rows.extend(cur.fetchall())
        data: dict[str, dict[str, Any]] = {}
        for row in rows:
            data[row[0]] = self._expand_results_row(row)
        return data

    def _expand_results_row(self, row: list[Any]) -> dict[str, Any]:
        d: dict[str, Any] = {}
        d["id"] = row[0]
        d["spec_name"] = row[1]
        d["spec_fullname"] = row[2]
        d["session"] = row[3]
        d["status"] = Status.from_dict(
            {
                "state": row[4],
                "category": row[5],
                "status": row[6],
                "reason": row[7],
                "code": row[8],
            }
        )
        d["timekeeper"] = Timekeeper.from_dict(
            {
                "started_on": row[9],
                "finished_on": row[10],
                "duration": float(row[11]),
            }
        )
        d["workspace"] = row[12]
        d["measurements"] = Measurements.from_dict(json.loads(row[13]))
        return d

    def get_single_result(self, id: str) -> list:
        rows = self.connection.execute(
            "SELECT * FROM results WHERE id LIKE ? ORDER BY session ASC", (f"{id}%",)
        ).fetchall()
        data: list[dict] = []
        for row in rows:
            d = self._expand_results_row(row)
            data.append(d)
        return data

    def get_dependency_graph(self) -> dict[str, list[str]]:
        rows = self.connection.execute("SELECT id, data FROM dependencies;").fetchall()
        return {id: json.loads(data) for id, data in rows}

    def put_selection(self, tag: str, snapshot: select.SelectorSnapshot) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO selections (tag, data)
                VALUES (?, ?)
                ON CONFLICT(tag) DO UPDATE SET data=excluded.data
                """,
                (tag, snapshot.serialize()),
            )

    def get_selection(self, tag: str) -> select.SelectorSnapshot:
        row = self.connection.execute("SELECT * FROM selections WHERE tag = ?", (tag,)).fetchone()
        if row is None:
            raise NotASelection(tag)
        snapshot = select.SelectorSnapshot.reconstruct(row[1])
        return snapshot

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


class WorkspaceExistsError(Exception):
    pass


class NotAWorkspaceError(Exception):
    pass


class SpecNotFoundError(Exception):
    pass


class NotASelection(Exception):
    def __init__(self, tag):
        super().__init__(f"No selection for tag {tag!r} found")
