# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Workspace management for Canary test execution.

This module defines the `Workspace` and `Session` classes which handle the lifecycle of test
execution environments. A Workspace acts as the central repository for test specifications, results
databases, and "views" (consolidated results). Sessions represent a specific execution run of a set
of jobs.

Key functionalities include:
    - Creating and loading persistent workspaces on disk.
    - Managing a "View" of the latest test results via symlinks, hardlinks, or copies.
    - Coordinating the execution of `Job` objects within a `Session`.
    - Interfacing with the `WorkspaceDatabase` to store and retrieve job specifications.
    - Providing selection mechanisms to filter tests by tags, regex, or owners.

Example:
    >>> ws = Workspace.create(path=".")
    >>> specs = ws.collect(scanpaths={"/src/tests": []})
    >>> session = ws.run(specs=specs)
"""

import dataclasses
import datetime
import fnmatch
import os
import shutil
from enum import Enum
from enum import auto
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal

import yaml

from . import config
from . import jobspec
from . import rules
from . import select
from . import version
from .collect import Collector
from .database import WorkspaceDatabase
from .error import StopExecution
from .error import notests_exit_status
from .generate import Generator
from .generator import AbstractTestGenerator
from .job import Dependency
from .job import Job
from .runtest import Runner
from .runtest import canary_runtests
from .testexec import ExecutionSpace
from .util import json_helper as json
from .util import logging
from .util.filesystem import async_rmtree
from .util.filesystem import force_remove
from .util.filesystem import write_directory_tag
from .util.graph import static_order
from .util.names import unique_random_name

if TYPE_CHECKING:
    from .database import ResultListener
    from .jobspec import JobSpec
    from .queue_executor import EventTypes

logger = logging.get_logger(__name__)

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
view_tag = "VIEW.TAG"
workspace_log = "canary.log"


DB_MAX_RETRIES = 8
DB_BASE_DELAY = 0.05  # 50ms base for exponential backoff (0.05, 0.1, 0.2, ...)
SQL_CHUNK_SIZE = 900


@dataclasses.dataclass
class ViewSettings:
    name: str = "TestResults"
    when: Literal["always", "on_success", "on_failure", "never"] = "always"
    only: Literal["all", "failed", "not_pass", "passed"] = "all"
    mode: Literal["symlink", "hardlink", "copy"] = "symlink"

    @classmethod
    def default(cls) -> "ViewSettings":
        view_cfg = config.get("workspace:view") or {}
        name = view_cfg.get("name") or "TestResults"
        when = view_cfg.get("when") or "always"
        only = view_cfg.get("only") or "all"
        mode = view_cfg.get("mode") or "symlink"
        return ViewSettings(name=name, when=when, only=only, mode=mode)

    def __serialize__(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "ViewSettings":
        return cls(**d)

    def __post_init__(self):
        assert os.path.sep not in self.name
        assert self.when in {"on_success", "on_failure", "always", "never"}
        assert self.only in {"all", "failed", "not_pass", "passed"}
        assert self.mode in {"symlink", "hardlink", "copy"}

    def include_job(self, job: Job) -> bool:
        if job.status.is_skipped():
            return False
        if self.only == "failed" and not job.status.is_failure():
            return False
        elif self.only == "passed" and not job.status.is_success():
            return False
        elif self.only == "not_pass" and job.status.is_success():
            return False
        return True

    def is_enabled(self, jobs: list[Job]) -> bool:
        if self.always_disabled():
            return False
        elif self.always_enabled():
            return True
        outcome = SessionOutcome.from_jobs(jobs)
        if self.when == "on_success":
            return outcome == SessionOutcome.PASS
        if self.when == "on_failure":
            return outcome != SessionOutcome.PASS
        raise AssertionError(f"unexpected when={self.when!r}")

    def always_disabled(self) -> bool:
        return self.when == "never"

    def always_enabled(self) -> bool:
        return self.when == "always"


@dataclasses.dataclass(frozen=True)
class ResultsView:
    root: Path
    settings: ViewSettings

    def __serialize__(self) -> dict[str, Any]:
        # json_helper.Encoder will add ".type" automatically
        return {"root": self.root, "settings": self.settings}

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "ResultsView":
        return cls(root=Path(d["root"]), settings=d["settings"])

    @property
    def dir(self) -> Path:
        return (self.root / self.settings.name).resolve()

    def exists(self) -> bool:
        return self.dir.exists() and (self.dir / view_tag).exists()

    def make(self, exist_ok: bool = False) -> None:
        tag = self.dir / view_tag
        if self.dir.exists():
            if not tag.exists():
                raise ValueError("Cannot create view in non-owning directory")
            elif not exist_ok:
                raise ValueError(f"View already exists at {self.dir}")
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        write_directory_tag(tag)

    def unlink(self, missing_ok: bool = False) -> None:
        if not self.dir.exists():
            if not missing_ok:
                raise ValueError(f"View does not exist at {self.dir}")
            return
        tag = self.dir / view_tag
        if self.dir.exists() and not tag.exists():
            raise ValueError("Cannot remove non-owning directory")
        force_remove(self.dir)

    def update(self, jobs: list[Job]) -> bool:
        if not self.settings.is_enabled(jobs):
            return False
        for job in jobs:
            self.maybe_add(job)
        return True

    def maybe_add(self, job: Job) -> bool:
        if not self.settings.include_job(job):
            return False
        self.add(job)
        return True

    def add(self, job: Job) -> None:
        source = job.workspace.dir
        dest = self.dir / job.view_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            force_remove(dest)
        if self.settings.mode == "symlink":
            try:
                dest.symlink_to(source, target_is_directory=True)
            except FileExistsError:
                pass
        elif self.settings.mode == "hardlink":
            # Mirror the directory tree with hardlinks for files.
            # (Hardlinks don't work across filesystems; will raise OSError in this job.)
            for src in source.rglob("*"):
                rel = src.relative_to(source)
                dst = dest / rel
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
                os.link(src, dst)
        elif self.settings.mode == "copy":
            # Copy the directory tree
            shutil.copytree(source, dest, dirs_exist_ok=True, symlinks=False)


class SessionOutcome(Enum):
    PASS = auto()
    FAIL = auto()
    INCONCLUSIVE = auto()

    @classmethod
    def from_jobs(cls, jobs: list[Job]) -> "SessionOutcome":
        any_success: bool = False
        for job in jobs:
            if job.status.is_failure():
                return cls.FAIL
            if job.status.is_success():
                any_success = True
        return cls.PASS if any_success else cls.INCONCLUSIVE


@dataclasses.dataclass
class Session:
    name: str
    jobs: list[Job]
    prefix: Path
    returncode: int = dataclasses.field(init=False, default=-1)
    started_on: datetime.datetime = dataclasses.field(init=False, default=datetime.datetime.min)
    finished_on: datetime.datetime = dataclasses.field(init=False, default=datetime.datetime.min)

    def __post_init__(self) -> None:
        """Validates session jobs.

        Raises:
            ValueError: If any job in the session is unexpectedly masked.
        """
        for job in self.jobs:
            if job.mask:
                raise ValueError(f"{job}: unexpectedly masked test job")

    def run(self, workspace: "Workspace") -> None:
        """Executes the session's jobs using a Runner.

        Args:
            workspace: The Workspace instance providing the environment.

        Raises:
            StopExecution: If no runnable jobs are found.
        """
        self.prefix.mkdir(parents=True, exist_ok=True)
        ready = [job for job in self.jobs if job.is_runnable()]
        runner = Runner(ready, self.name, workspace=workspace)
        if not ready:
            exit_code = 0 if config.getoption("empty_ok") else notests_exit_status
            raise StopExecution("no jobs to run", exit_code=exit_code)
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
        """Internal constructor. Use `Workspace.create()` or `Workspace.load()`."""
        # Even through this function is not meant to be called, we declare types so that code
        # editors know what to work with.
        self.root: Path

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

        self.db: WorkspaceDatabase

        self.canary_level: int

        raise RuntimeError("Use Workspace factory methods create and load")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def initialize_properties(self, *, anchor: Path) -> None:
        """Sets up the internal directory structure paths based on the anchor.

        Args:
            anchor: The base directory where the .canary folder resides.
        """
        self.root = anchor / workspace_path
        self.refs_dir = self.root / "refs"
        self.sessions_dir = self.root / "sessions"
        self.cache_dir = self.root / "cache"
        self.tmp_dir = self.root / "tmp"
        self.logs_dir = self.root / "logs"
        self.canary_level = 0
        if var := os.getenv("CANARY_LEVEL_OVERRIDE"):
            self.canary_level = int(var)
        elif var := os.getenv("CANARY_LEVEL"):
            self.canary_level = int(var)

    @staticmethod
    def remove(start: str | Path = Path.cwd()) -> Path | None:
        """Deletes a workspace and its associated view.

        Args:
            start: Path to start searching for the workspace.

        Returns:
            The path to the removed workspace, or None if no workspace was found.
        """
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
        if view is None or not view.exists():
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
        """Dangerously removes the workspace and view directories from disk."""
        if view := self.latest_view():
            async_rmtree(view.dir)
        async_rmtree(self.root)

    def latest_view(self) -> ResultsView | None:
        file = self.cache_dir / "view"
        if file.exists():
            view = json.loads(file.read_text())
            return view
        return None

    def register_view(self, view: ResultsView) -> None:
        (self.cache_dir / "view").write_text(json.dumps(view, indent=2))

    @staticmethod
    def find_anchor(start: str | Path = Path.cwd()) -> Path | None:
        """Searches upwards from start to find the directory containing the workspace.

        Args:
            start: The directory to start the search from.

        Returns:
            The anchor Path if found, otherwise None.
        """
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
        """Locates the .canary workspace directory.

        Args:
            start: The directory to start the search from.

        Returns:
            The path to the workspace directory if found, otherwise None.
        """
        if anchor := Workspace.find_anchor(start=start):
            return anchor / workspace_path
        return None

    @classmethod
    def create(cls, path: str | Path = Path.cwd(), force: bool = False) -> "Workspace":
        """Creates a new Canary workspace at the specified path.

        Args:
            path: The anchor directory for the workspace.
            force: If True, remove existing workspace at path before creating.

        Returns:
            The newly created Workspace instance.
        """
        path = Path(path).absolute()
        if path.stem == workspace_path:
            raise ValueError(f"Don't include {workspace_path} in workspace path")
        if force:
            cls.remove(start=path)
        wspath = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        logger.info(f"[bold]Initializing[/] empty canary workspace at {wspath}")
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

        self.db = WorkspaceDatabase.create(self.root)
        file = self.root / "config.yaml"
        cfg: dict[str, Any] = {}
        if mods := config.getoption("config_mods"):
            cfg.update(mods)
        with open(file, "w") as fh:
            yaml.dump({"canary": cfg}, fh, default_flow_style=False)

        return self

    @classmethod
    def load(cls, start: str | Path | None = None) -> "Workspace":
        """Loads an existing workspace from the filesystem.

        Args:
            start: The directory to start searching for the workspace.

        Returns:
            A loaded Workspace instance.

        Raises:
            NotAWorkspaceError: If no workspace is found.
        """
        start = Path(start or Path.cwd())
        logger.debug(f"Loading Canary workspace from {start}")
        anchor = cls.find_anchor(start=start)
        if anchor is None:
            raise NotAWorkspaceError(
                f"not a Canary workspace (or any of its parent directories): {workspace_path}"
            )
        self: Workspace = object.__new__(cls)
        self.initialize_properties(anchor=anchor)
        self.db = WorkspaceDatabase.load(self.root)
        return self

    def run(
        self,
        specs: list["JobSpec"],
        session: str | None = None,
        inplace: bool = False,
        view_t: ViewSettings | None = None,
        only: str = "not_pass",
    ) -> Session:
        """Executes a set of job specifications in a new or existing session.

        Args:
            specs: List of job specs to run.
            session: Optional existing session name to reuse.
            inplace: If True, run jobs in their existing result directories.
            view_t: View settings.
            only: Rerun strategy (e.g., 'not_pass').

        Returns:
            The resulting Session object.
        """
        reuse_session: bool = session is not None
        if session is not None and not (self.sessions_dir / session).exists():
            raise ValueError(f"Session {session} not found in {self.sessions_dir}")
        now = datetime.datetime.now()
        session_name = session or now.isoformat(timespec="microseconds").replace(":", "-")
        session_dir = self.sessions_dir / session_name
        jobs = self.construct_jobs(specs, session_dir)
        selector = select.RuntimeSelector(jobs, workspace=self.root)
        selector.add_rule(rules.ResourceCapacityRule())
        selector.add_rule(rules.RerunRule(strategy=only))
        selector.run()

        # At this point, test jobs have been reconstructed and, if previous results exist,
        # restored to their last ran state.  If inplace, we leave the test job as is.
        # Otherwise, we swap out the old session for the new.
        ready: list["Job"] = []
        for job in jobs:
            if job.mask:
                continue
            elif inplace:
                if not job.workspace.dir.exists():
                    raise RuntimeError(f"{job}: requested to run in place but results do not exist")
            else:
                # Force override session dir
                job.workspace.root = session_dir
                job.workspace.session = session_dir.name
                if session is not None:
                    assert job.workspace.session == session, f"{job}: unexpected workspace"
            ready.append(job)

        s = Session(name=session_dir.name, prefix=session_dir, jobs=ready)
        if not reuse_session:
            config.pluginmanager.hook.canary_sessionstart(session=s)

        # We need to take great care to only write results into the database from the parent process
        # On the parent process, create a results listener that looks for results in the spool.
        # As test jobs finish, the testcase_done_callback is called and the results put into the
        # spool.  When the listener detects the results, it will write them to the database.  This
        # way, the database is only receiving results from a single writer.  Otherwise, results can
        # be written from many writers originating from many different processes (eg, a canary
        # instance launched inside a HPC scheduler)
        self.db.close()
        listener: "ResultListener | None" = None
        if self.canary_level == 0:
            listener = self.db.listener()
            listener.start()
        s.run(workspace=self)
        if listener is not None:
            listener.stop_and_join()
            not_saved = [job for job in s.jobs if job.id not in listener._processed]
            self.db.put_results(*not_saved)
        if not reuse_session:
            config.pluginmanager.hook.canary_sessionfinish(session=s)
        self.add_session_results(s, view_t=view_t)
        return s

    def add_session_results(self, session: Session, view_t: ViewSettings | None = None) -> None:
        """Update latest results, view, and refs with results from ``session``"""
        if view_t is None:
            last = self.latest_view()
            view_t = last.settings if last is not None else ViewSettings.default()
        if not view_t.always_disabled():
            view = ResultsView(root=self.root.parent, settings=view_t)
            logger.info(f"Updating view at {view.dir}")
            view.make(exist_ok=True)
            if view.update(session.jobs):
                self.register_view(view)
        # Write meta data file refs/latest -> ../sessions/{session.root}
        file = self.refs_dir / "latest"
        file.unlink(missing_ok=True)
        link = os.path.relpath(str(session.prefix), str(file.parent))
        file.write_text(str(link))

    def rebuild_view(self, view_t: ViewSettings | None = None) -> None:
        """Keep only the latest results."""
        logger.info(f"Rebuilding view at {self.root}")
        jobs = self.load_jobs()

        old_view = self.latest_view()
        old_dir: str | None = None
        bak_dir: str | None = None

        if old_view is not None and old_view.exists():
            old_dir = str(old_view.dir)
            bak_dir = old_dir + ".tmp"
            os.rename(old_dir, bak_dir)
            if view_t is None:
                view_t = old_view.settings

        made_new = False
        try:
            settings = view_t or ViewSettings.default()
            if settings.always_disabled():
                made_new = False
                return
            view = ResultsView(root=self.root.parent, settings=settings)
            # ensure we start clean (there shouldn't be anything at view.dir now,
            # since we renamed old_dir away, but this keeps it robust)
            view.unlink(missing_ok=True)
            view.make()
            if view.update(jobs):
                self.register_view(view)
                made_new = True
            else:
                view.unlink(missing_ok=True)
                made_new = False
        finally:
            # If we built and registered a new view, remove the backup.
            if made_new:
                if bak_dir is not None:
                    force_remove(bak_dir)
            # Otherwise restore the previous view, if we had one.
            else:
                if bak_dir is not None and old_dir is not None:
                    if not os.path.exists(old_dir) and os.path.exists(bak_dir):
                        os.rename(bak_dir, old_dir)

    def relative_to_view(self, path: str | os.PathLike[str]) -> str | None:
        """
        If `path` is inside TestResults, return the relative path (which
        may include glob characters). Otherwise return None.

        Examples:
          /ws/TestResults/foo/bar/test.py  -> foo/bar/test.py
        """
        if latest_view := self.latest_view():
            p = Path(path).absolute()
            if p.is_relative_to(latest_view.dir):
                return str(p.relative_to(latest_view.dir))
        return None

    def is_session_dir(self, path: str | os.PathLike[str]) -> bool:
        """Checks if a path is located within the workspace's sessions directory.

        Args:
            path: The path to check.

        Returns:
            True if the path is inside the sessions directory, False otherwise.
        """
        p = Path(path).absolute()
        return p.is_relative_to(self.sessions_dir)

    def info(self) -> dict[str, Any]:
        """Returns summary information about the workspace.

        Returns:
            A dictionary containing root, session count, latest session, and version.
        """
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
            "specs": self.db.load_specs(),
            "version": version.__version__,
            "workspace_version": (self.root / "VERSION").read_text().strip(),
        }
        return info

    def collect(
        self,
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
    ) -> list["JobSpec"]:
        """Find test job generators in scan_paths and add them to this workspace.

        Args:
            scanpaths: Dictionary of root paths to scan.
            on_options: Options used to filter tests by option.

        Returns:
            A list of resolved JobSpecs.
        """
        collector = Collector()
        collector.add_scanpaths(scanpaths)
        generators = collector.run()
        resolved = self.generate_jobspecs(generators=generators, on_options=on_options)
        self.store_specs(resolved)
        return resolved

    def store_specs(self, specs: list["JobSpec"]) -> None:
        """Caches the provided job specifications into the workspace database.

        Args:
            specs: The resolved job specifications to store.
        """
        pm = logger.progress_monitor("[bold]Caching[/] test specs")
        self.db.put_specs(specs)
        pm.done()

    def select(
        self,
        tag: str,
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Selects job specifications from the database using filters and saves as a tag.

        Args:
            tag: The name of the selection tag to create.
            prefixes: Filter by path prefixes.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameter expressions.
            owners: Filter by owners.
            regex: Filter by regular expression.

        Returns:
            The list of selected JobSpecs.
        """
        resolved = self.db.load_specs()
        specs = self.select_from_specs(
            resolved,
            prefixes=prefixes,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        self.db.put_selection(
            tag,
            specs,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        return specs

    def select_from_specs(
        self,
        resolved: list["JobSpec"],
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Filters a list of JobSpecs using the provided rules.

        Args:
            resolved: The list of specs to filter.
            prefixes: Filter by path prefixes.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameter expressions.
            owners: Filter by owners.
            regex: Filter by regular expression.

        Returns:
            The filtered list of JobSpecs.
        """
        selector = select.Selector(resolved, self.root)
        if keyword_exprs:
            selector.add_rule(rules.KeywordRule(keyword_exprs))
        if parameter_expr:
            selector.add_rule(rules.ParameterRule(parameter_expr))
        if owners:
            selector.add_rule(rules.OwnersRule(owners))
        if regex:
            selector.add_rule(rules.RegexRule(regex))
        if prefixes:
            selector.add_rule(rules.PrefixRule(prefixes=prefixes))
        specs = selector.run()
        return specs

    def create_selection(
        self,
        tag: str | None,
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Collects generators from paths and creates a tagged selection.

        Args:
            tag: Tag name (randomly generated if None).
            scanpaths: Paths to scan for generators.
            on_options: Options to filter tests by.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameters.
            owners: Filter by owners.
            regex: Filter by regex.

        Returns:
            The created selection of JobSpecs.
        """
        resolved = self.collect(scanpaths, on_options=on_options)
        specs = self.select_from_specs(
            resolved,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        tag = tag or unique_random_name(self.db.tags)
        self.db.put_selection(
            tag,
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
        specs: list["JobSpec"],
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Filters the provided specs in-place using selection rules.

        Args:
            specs: The list of specs to filter.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameters.
            owners: Filter by owners.
            regex: Filter by regex.
            ids: Filter by specific IDs.
        """
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

    def load_jobs(self, ids: list[str] | None = None) -> list[Job]:
        """Loads jobs from the database, reconstructing them with their latest results.

        Args:
            ids: Optional list of specific job IDs to load.

        Returns:
            A list of Job objects in static dependency order.
        """
        lookup: dict[str, Job] = {}
        latest = self.db.get_results(ids, include_upstreams=True)
        specs = self.db.load_specs(ids, include_upstreams=True)
        for spec in static_order(specs):
            if mine := latest.get(spec.id):
                deps = [Dependency(job=lookup[d.spec.id], when=d.when) for d in spec.dependencies]
                space = ExecutionSpace(
                    root=self.sessions_dir / mine["session"],
                    path=Path(mine["workspace"]),
                    session=mine["session"],
                )
                job = Job(spec=spec, workspace=space, dependencies=deps)
                job.status = mine["status"]
                job.timekeeper = mine["timekeeper"]
                job.measurements = mine["measurements"]
                job.state = mine["state"]
                lookup[spec.id] = job
        if ids:
            return [job for job in lookup.values() if job.id in ids]
        return list(lookup.values())

    def select_from_view(
        self,
        path: Path,
    ) -> list["JobSpec"]:
        """Identifies JobSpecs based on 'testcase.lock' files found in the view.

        Args:
            path: The directory path to scan for lock files.

        Returns:
            A list of corresponding JobSpecs.
        """
        ids: list[str] = []
        for file in path.rglob("*/testcase.lock"):
            job = json.loads(file.read_text())
            ids.append(job.spec.id)
        resolved = self.db.load_specs(ids=ids)
        return resolved

    def remove_tag(self, tag: str) -> bool:
        """Deletes a selection tag from the database.

        Args:
            tag: The tag name to remove.

        Returns:
            True if the tag was removed, False if it didn't exist.
        """
        if not self.db.is_selection(tag):
            logger.error(f"{tag!r} is not a tag")
            return False
        self.db.delete_selection(tag)
        return True

    def is_tag(self, tag: str) -> bool:
        """Checks if a given string is a valid selection tag.

        Args:
            tag: The string to check.

        Returns:
            True if it is a selection tag, False otherwise.
        """
        return self.db.is_selection(tag)

    def generate_jobspecs(
        self,
        generators: list["AbstractTestGenerator"],
        on_options: list[str] | None = None,
    ) -> list["JobSpec"]:
        """Generate resolved test specs.

        Args:
            generators: List of test generators.
            on_options: Used to filter tests by option.

        Returns:
            A list of resolved JobSpecs.
        """
        on_options = on_options or []
        generator = Generator(generators, workspace=self.root, on_options=on_options or [])
        resolved = generator.run()
        return resolved

    def construct_jobs(self, specs: list["JobSpec"], session: Path) -> list["Job"]:
        """Creates Job objects from JobSpecs, attempting to link latest results.

        Args:
            specs: The specifications to turn into jobs.
            session: The directory for the current session.

        Returns:
            A list of constructed Job objects.
        """
        lookup: dict[str, Job] = {}
        jobs: list[Job] = []
        latest = self.db.get_results([spec.id for spec in specs])
        for spec in static_order(specs):
            deps = [Dependency(job=lookup[d.spec.id], when=d.when) for d in spec.dependencies]
            job: Job
            if spec.id in latest:
                # This job won't run, but it may be needed by dependents
                mine = latest[spec.id]
                space = ExecutionSpace(
                    root=self.sessions_dir / mine["session"],
                    path=Path(mine["workspace"]),
                    session=mine["session"],
                )
                job = Job(spec=spec, workspace=space, dependencies=deps)
                job.status = mine["status"]
                job.state = mine["state"]
                job.timekeeper = mine["timekeeper"]
                job.measurements = mine["measurements"]
            else:
                space = ExecutionSpace(root=session, path=spec.exec_path, session=session.name)
                job = Job(spec=spec, workspace=space, dependencies=deps)
            lookup[spec.id] = job
            jobs.append(job)
        return jobs

    def get_selection(self, tag: str | None) -> list["JobSpec"]:
        """Retrieves a list of JobSpecs associated with a tag.

        Args:
            tag: The tag name, or None/:all: for all specs.

        Returns:
            A list of JobSpecs.
        """
        if tag is None or tag == ":all:":
            return self.db.load_specs()
        return self.db.load_specs_by_tagname(tag)

    def gc(self, dryrun: bool = False) -> None:
        """Garbage collects old result directories, keeping only the latest per job.

        Args:
            dryrun: If True, only log what would be removed without actually deleting.
        """
        raise NotImplementedError

        def mtime(path: Path):
            return path.stat().st_mtime

        logger.info(f"Garbage collecting {self.root}")
        latest: dict[str, Job] = {}
        view: dict[str, tuple[str, str]] = {}
        to_remove: list[Job] = []
        for session in self.sessions():
            for job in session.jobs:
                if job.id not in latest:
                    latest[job.id] = job
                elif mtime(latest[job.id].workspace.dir) > mtime(job.workspace.dir):
                    to_remove.append(latest[job.id])
                    latest[job.id] = job
                else:
                    continue
                ws_dir = latest[job.id].workspace.dir
                relpath = ws_dir.relative_to(session.work_dir)
                view[job.id] = (str(session.work_dir), str(relpath))
        try:
            for job in to_remove:
                logger.info(f"gc: removing {job}::{job.workspace.dir}")
                if not dryrun:
                    job.workspace.remove()
        finally:
            logger.info(f"Garbage collected {len(to_remove)} test jobs")
            if not dryrun:
                view_entries: dict[Path, list[Path]] = {}
                for root, path in view.values():
                    view_entries.setdefault(Path(root), []).append(Path(path))
                self.update_view(view_entries)

    def find(self, *, job: str | None = None, spec: str | None = None) -> Any:
        """Locates a Job or JobSpec in the workspace.

        Args:
            job: Identifier to find a Job.
            spec: Identifier to find a JobSpec.

        Returns:
            The found Job or JobSpec.
        """
        assert not (job and spec)
        if job is not None:
            return self.find_job(job)
        if spec is not None:
            return self.find_jobspec(spec)

    def find_job(self, root: str) -> Job:
        """Locates a Job by ID or matching pattern.

        Args:
            root: The ID or pattern to match.

        Returns:
            The matching Job object.

        Raises:
            ValueError: If no matching job is found.
        """
        id = self.db.resolve_spec_id(root)
        if id is not None:
            try:
                return self.load_jobs([id])[0]
            except IndexError:
                raise ValueError(f"{id}: no matching test job found in {self.root}")
        # Do the full (slow) lookup
        jobs = self.load_jobs()
        for job in jobs:
            if job.spec.matches(root):
                return job
        raise ValueError(f"{root}: no matching test job found in {self.root}")

    def find_jobspec(self, root: str) -> "JobSpec":
        """Locates a JobSpec by ID or matching pattern.

        Args:
            root: The ID or pattern to match.

        Returns:
            The matching JobSpec object.

        Raises:
            ValueError: If no matching spec is found.
        """
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
        """Resolves a list of potentially partial IDs or names to full spec IDs.

        Args:
            ids: List of strings to resolve.

        Returns:
            A list of resolved spec IDs, or None if not found.
        """
        specs = self.db.load_specs()
        found: list[str | None] = []
        for id in ids:
            if id.startswith(jobspec.select_sygil):
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

    def testcase_done_callback(self, event: "EventTypes", *args: Any) -> None:
        """Callback to queue job results for database persistence.

        Args:
            event: The event type.
            *args: Event arguments, expected to contain the finished job.
        """
        if event == "job_finished":
            self.db.queue.put(args[0].job)


class WorkspaceExistsError(Exception):
    """Raised when attempting to create a workspace in a directory that already exists."""

    pass


class NotAWorkspaceError(Exception):
    """Raised when a directory is not recognized as a Canary workspace."""

    pass


class SpecNotFoundError(Exception):
    """Raised when a requested JobSpec cannot be located in the workspace."""

    pass
