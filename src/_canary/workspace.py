# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import shutil
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Generator

from . import config
from . import rules
from . import select
from . import testspec
from . import when
from .build import Builder
from .build import canary_build
from .collect import Collector
from .collect import canary_collect
from .generator import AbstractTestGenerator
from .session import Session
from .session import SessionResults
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import ResolvedSpec
from .testspec import TestSpec
from .util import json_helper as json
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import write_directory_tag
from .util.graph import TopologicalSorter
from .util.graph import reachable_nodes
from .util.graph import static_order

logger = logging.get_logger(__name__)

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
view_tag = "VIEW.TAG"


DB_MAX_RETRIES = 8
DB_BASE_DELAY = 0.05  # 50ms base for exponential backoff (0.05, 0.1, 0.2, ...)


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
        self._spec_ids: set[str] = set()

    @staticmethod
    def remove(start: str | Path = Path.cwd()) -> Path | None:
        relpath = Path(start).absolute().relative_to(Path.cwd())
        pm = logger.progress_monitor(f"Removing workspace from {relpath}")
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
            pm.done(f"error: unaable to remove {workspace}")
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
        logger.info(f"Initializing empty canary workspace at {path}")
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
        file.write_text(json.dumps({"canary": {}}))

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

    def sessions(self) -> Generator[Session, None, None]:
        for path in self.sessions_dir.iterdir():
            if Session.is_session(path):
                yield Session.load(path)

    @contextmanager
    def session(
        self, specs: list["TestSpec"] | None = None, name: str | None = None
    ) -> Generator[Session, None, None]:
        session: Session
        if specs is not None and name is not None:
            raise TypeError("Mutually exlusive keyword arguments: 'specs', 'name'")
        elif specs is None and name is None:
            raise TypeError("Missing required keyword arguments: 'specs' or 'name'")
        if specs is not None:
            session = Session.create(self.sessions_dir, specs)
            logger.info(f"Created test session at {session.name}")
        else:
            assert name is not None
            root = self.sessions_dir / name
            session = Session.load(root)
            logger.info(f"Loaded test session at {session.name}")
        try:
            config.pluginmanager.hook.canary_sessionstart(session=session)
            yield session
        finally:
            config.pluginmanager.hook.canary_sessionfinish(session=session)

    def add_session_results(self, results: SessionResults, view: bool = True) -> None:
        """Update latest results, view, and refs with results from ``session``"""
        self.db.put_results(results)
        view_entries: dict[Path, list[Path]] = {}
        for case in results.cases:
            relpath = case.workspace.dir.relative_to(results.prefix / "work")
            view_entries.setdefault(results.prefix / "work", []).append(relpath)

        if view:
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

        def mtime(path: Path):
            return path.stat().st_mtime

        latest: dict[str, TestCase] = {}
        view: dict[str, tuple[str, str]] = {}
        for session in self.sessions():
            for case in session.cases:
                if case.id not in latest:
                    latest[case.id] = case
                elif mtime(latest[case.id].workspace.dir) > mtime(case.workspace.dir):
                    latest[case.id] = case
                else:
                    continue
                ws_dir = latest[case.id].workspace.dir
                relpath = ws_dir.relative_to(session.work_dir)
                view[case.id] = (str(session.work_dir), str(relpath))
        for path in self.view.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
        view_entries: dict[Path, list[Path]] = {}
        for root, p in view.values():
            view_entries.setdefault(Path(root), []).append(Path(p))
        self.update_view(view_entries)

    def update_view(self, view_entries: dict[Path, list[Path]]) -> None:
        logger.info(f"@*{{Updating}} view at {self.view}")
        if self.view is None:
            return
        for root, paths in view_entries.items():
            for path in paths:
                target = root / path
                link = self.view / path
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists():
                    link.unlink()
                link.symlink_to(target, target_is_directory=True)

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
        generators = self.db.get_generators()
        generator_count = len(generators)
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
        pm = logger.progress_monitor("@*{Loading} test case generators from workspace database")
        generators = self.db.get_generators()
        pm.done()
        return generators

    def active_testcases(self) -> list[TestCase]:
        return self.load_testcases()

    def add(
        self, scanpaths: dict[str, list[str]], pedantic: bool = True
    ) -> list[AbstractTestGenerator]:
        """Find test case generators in scan_paths and add them to this workspace"""
        collector = Collector()
        collector.add_scanpaths(scanpaths)
        generators = canary_collect(collector)
        self.db.put_generators(generators)
        # Invalidate caches
        logger.info(f"@*{{Added}} {len(generators)} new test case generators to {self.root}")
        return generators

    def load_testcases(self, ids: list[str] | None = None) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed.  If ``latest is True``,
        update each case to point to the latest run instance.
        """
        lookup: dict[str, TestCase] = {}
        reachable: list[str] | None = None
        if ids:
            reachable = self.db.reachable_spec_ids(ids)
        resolved = self.db.get_specs(ids=reachable)
        latest = self.db.get_results(ids=reachable)
        specs = select.finalize(resolved)
        for spec in static_order(specs):
            if mine := latest.get(spec.id):
                dependencies = [lookup[dep.id] for dep in spec.dependencies]
                space = ExecutionSpace(
                    root=Path(mine["workspace"]["root"]),
                    path=Path(mine["workspace"]["path"]),
                    session=mine["workspace"]["session"],
                )
                case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
                case.status.set(
                    mine["status"]["name"],
                    message=mine["status"]["message"],
                    code=mine["status"]["code"],
                )
                case.timekeeper.started_on = mine["timekeeper"]["started_on"]
                case.timekeeper.finished_on = mine["timekeeper"]["finished_on"]
                case.timekeeper.duration = mine["timekeeper"]["duration"]
                lookup[spec.id] = case
        if ids:
            return [case for case in lookup.values() if case.id in ids]
        return list(lookup.values())

    def select_from_path(
        self,
        path: Path,
        keyword_exprs: list[str] | None = None,
    ) -> list[TestCase]:
        ids: list[str] = []
        for file in path.rglob("testcase.lock"):
            lock_data = json.loads(file.read_text())
            ids.append(lock_data["spec"]["id"])
        cases = self.load_testcases(ids=ids)
        if keyword_exprs is None:
            return cases
        masks: dict[str, bool] = {}
        for case in cases:
            kwds = set(case.spec.keywords)
            kwds.update(case.spec.implicit_keywords)
            kwd_all = (":all:" in keyword_exprs) or ("__all__" in keyword_exprs)
            if not kwd_all:
                for keyword_expr in keyword_exprs:
                    match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                    if not match:
                        masks[case.id] = True
                        break
        return [case for case in cases if not masks.get(case.id)]

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

    def generate_specs(self, on_options: list[str] | None = None) -> list[ResolvedSpec]:
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
        builder = Builder(generators, workspace=self.root, on_options=on_options or [])
        signature = builder.signature
        if cached := self.db.get_specs(signature=signature):
            return cached
        resolved = canary_build(builder)
        pm = logger.progress_monitor("@*{Putting} specs in workspace database")
        self.db.put_specs(signature, resolved)
        pm.done()
        return resolved

    def select(
        self,
        tag: str | None = None,
        prefixes: list[str] | None = None,
        on_options: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
    ) -> list["TestSpec"]:
        """Generate and select final test specs

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
          Test spec selection

        """
        specs = self.generate_specs(on_options=on_options)
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
        final = select.canary_select(selector=selector)
        if tag is None and len(selector.rules) == 1:
            # Default: 1 rule for resource availability
            tag = "default"
        if tag:
            self.db.put_selection(tag, selector.snapshot())
        return final

    def get_selection(self, tag: str = "default") -> list["TestSpec"]:
        if tag == "default" and not self.db.is_selection(tag):
            return self.select(tag="default")
        snapshot = self.db.get_selection(tag)
        specs = self.db.get_specs()
        if snapshot.is_compatible_with_specs(specs):
            return snapshot.apply(specs)
        selector = select.Selector.from_snapshot(specs, self.root, snapshot)
        selector.run()
        self.db.put_selection(tag, selector.snapshot())
        return selector.final_specs()

    def gc(self, dryrun: bool = False) -> None:
        """Keep only the latet results"""

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


def find_generators_in_path(path: str | Path) -> list[AbstractTestGenerator]:
    collector = Collector()
    collector.add_scanpath(str(path), [])
    generators = canary_collect(collector=collector)
    return generators


class WorkspaceDatabase:
    """Database wrapper for the "latest results" index."""

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
        """
        Create the 'LATEST' table if it doesn't exist.
        """
        self = cls(path)
        cursor = self.connection.cursor()

        query = "CREATE TABLE IF NOT EXISTS generators (id TEXT PRIMARY KEY, data TEXT)"
        cursor.execute(query)

        query = "CREATE TABLE IF NOT EXISTS specs (id TEXT PRIMARY KEY, signature TEXT, data TEXT)"
        cursor.execute(query)

        query = "CREATE TABLE IF NOT EXISTS dependencies (id TEXT PRIMARY KEY, data TEXT)"
        cursor.execute(query)

        query = "CREATE TABLE IF NOT EXISTS selections (tag TEXT PRIMARY KEY, data TEXT)"
        cursor.execute(query)

        query = """CREATE TABLE IF NOT EXISTS results (
          id TEXT PRIMARY KEY, status TEXT, timekeeper TEXT, workspace TEXT
        )"""
        cursor.execute(query)

        self.connection.commit()
        return self

    @classmethod
    def load(cls, path: Path) -> "WorkspaceDatabase":
        self = cls(path)
        return self

    def close(self):
        self.connection.close()

    def put_generators(self, generators: list[AbstractTestGenerator]) -> None:
        pm = logger.progress_monitor("@*{Putting} test generators into database")
        cursor = self.connection.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        rows = [(gen.id, gen.serialize()) for gen in generators]
        cursor.executemany(
            """
            INSERT INTO generators (id, data)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data
            """,
            rows,
        )
        self.connection.commit()
        pm.done()

    def get_generators(self) -> list[AbstractTestGenerator]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT data FROM generators;")
        rows = cursor.fetchall()
        with ProcessPoolExecutor() as ex:
            generators = list(ex.map(AbstractTestGenerator.reconstruct, [row[0] for row in rows]))
        return generators

    def put_specs(self, signature: str, specs: list[ResolvedSpec]) -> None:
        cursor = self.connection.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        cursor.executemany(
            """
            INSERT INTO specs (id, signature, data)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET signature=excluded.signature, data=excluded.data
            """,
            [(spec.id, signature, json.dumps_min(spec.asdict())) for spec in specs],
        )
        cursor.executemany(
            """
            INSERT INTO dependencies (id, data)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data
            """,
            [(spec.id, json.dumps_min([dep.id for dep in spec.dependencies])) for spec in specs],
        )
        self.connection.commit()

    def reachable_spec_ids(self, ids: list[str]) -> list[str]:
        graph = self.get_dependency_graph()
        self.resolve_spec_ids(ids)
        return reachable_nodes(graph, ids)

    def resolve_spec_id(self, id: str) -> str | None:
        if id.startswith(testspec.select_sygil):
            id = id[1:]
        cursor = self.connection.cursor()
        try:
            hi = increment_hex_prefix(id)
        except ValueError:
            return None
        if hi is None:
            return None
        cursor.execute("SELECT id FROM specs WHERE id >= ? AND id < ? LIMIT 2", (id, hi))
        rows = cursor.fetchall()
        if len(rows) == 0:
            return None
        elif len(rows) > 1:
            raise ValueError(f"Ambiguous spec ID {id!r}")
        return rows[0][0]

    def resolve_spec_ids(self, ids: list[str]):
        """Given partial spec IDs in ``ids``, expand them to their full size"""
        cursor = self.connection.cursor()
        for i, id in enumerate(ids):
            if id.startswith(testspec.select_sygil):
                id = id[1:]
            if len(id) >= 64:
                continue
            hi = increment_hex_prefix(id)
            assert hi is not None
            cursor.execute("SELECT id FROM specs WHERE id >= ? AND id < ? LIMIT 2", (id, hi))
            rows = cursor.fetchall()
            if len(rows) == 0:
                raise ValueError(f"No match for spec ID {id!r}")
            elif len(rows) > 1:
                raise ValueError(f"Ambiguous spec ID {id!r}")
            ids[i] = rows[0][0]

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
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM specs")
        rows = cursor.fetchall()
        return self._reconstruct_specs(rows)

    def _get_specs_by_signature(self, signature: str) -> list[ResolvedSpec]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM specs WHERE signature = ?", (signature,))
        rows = cursor.fetchall()
        return self._reconstruct_specs(rows)

    def _get_specs_by_exact_id(self, exact: list[str]) -> list[Any]:
        rows = list()
        cursor = self.connection.cursor()
        base_query = "SELECT * FROM specs WHERE id IN"
        if exact:
            while rem := len(exact) > 0:
                nvar = min(900, rem)
                placeholders = ",".join(["?"] * nvar)
                query = f"{base_query} ({placeholders})"
                cursor.execute(query, exact[:nvar])
                rows.extend(cursor.fetchall())
                exact = exact[nvar:]
        return rows

    def _get_specs_by_partial_id(self, partial: list[str]) -> list[Any]:
        rows = list()
        cursor = self.connection.cursor()
        base_query = "SELECT * FROM specs WHERE"
        if partial:
            while rem := len(partial) > 0:
                nvar = min(900, rem)
                clauses = " OR ".join(["id LIKE ?"] * nvar)
                params = [f"{p}%" for p in partial[:nvar]]
                query = f"{base_query} {clauses}"
                cursor.execute(query, params)
                rows.extend(cursor.fetchall())
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
        cursor = self.connection.cursor()
        cursor.execute(query, (signature, *params))
        rows = cursor.fetchall()
        specs = self._reconstruct_specs(rows)
        return [spec for spec in specs if spec.id in ids]

    def _reconstruct_specs(self, rows: list[list]) -> list[ResolvedSpec]:
        import time

        t = time.monotonic()
        data = {id: json.loads(data) for id, _, data in rows}
        graph = {id: [_["id"] for _ in s["dependencies"]] for id, s in data.items()}
        lookup: dict[str, ResolvedSpec] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            spec = ResolvedSpec.from_dict(data[id], lookup)
            lookup[id] = spec
        return list(lookup.values())

    def put_results(self, results: SessionResults) -> None:
        rows = []
        for case in results.cases:
            rows.append(
                (
                    case.id,
                    json.dumps_min(case.status.asdict()),
                    json.dumps_min(case.timekeeper.asdict()),
                    json.dumps_min(case.workspace.asdict()),
                )
            )
        cursor = self.connection.cursor()
        cursor.execute("BEGIN EXCLUSIVE;")
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
        self.connection.commit()

    def get_results(self, ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        cursor = self.connection.cursor()
        if not ids:
            cursor.execute("SELECT id, status, timekeeper, workspace  FROM results")
            rows = cursor.fetchall()
        else:
            clauses: list[str] = []
            params: list[str] = []
            for id in ids:
                if id.startswith(testspec.select_sygil):
                    id = id[1:]
                if len(id) >= 64:  # full sha256 hexdigest
                    clauses.append("id = ?")
                    params.append(id)
                else:
                    clauses.append("id LIKE ?")
                    params.append(f"{id}%")
            where = " OR ".join(f"({c})" for c in clauses)
            query = f"SELECT id, status, timekeeper, workspace FROM results WHERE {where}"  # nosec B608
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return {
            id: {
                "status": json.loads(status),
                "timekeeper": json.loads(timekeeper),
                "workspace": json.loads(workspace),
            }
            for id, status, timekeeper, workspace in rows
        }

    def get_dependency_graph(self) -> dict[str, list[str]]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT id, data FROM dependencies;")
        rows = cursor.fetchall()
        return {id: json.loads(data) for id, data in rows}

    def put_selection(self, tag: str, snapshot: select.SelectorSnapshot) -> None:
        cursor = self.connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            INSERT INTO selections (tag, data)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET data=excluded.data
            """,
            (tag, snapshot.serialize()),
        )
        self.connection.commit()

    def get_selection(self, tag: str) -> select.SelectorSnapshot:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM selections WHERE tag = ?", (tag,))
        row = cursor.fetchone()
        if row is None:
            raise NotASelection(tag)
        snapshot = select.SelectorSnapshot.reconstruct(row[1])
        return snapshot

    @property
    def tags(self) -> list[str]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT tag FROM selections")
        rows = cursor.fetchall()
        return [row[0] for row in rows]

    def is_selection(self, tag: str) -> bool:
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 FROM selections WHERE tag = ? LIMIT 1", (tag,))
        return cursor.fetchone() is not None

    def delete_selection(self, tag: str) -> bool:
        cursor = self.connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("DELETE FROM selections WHERE tag = ?", (tag,))
        self.connection.commit()
        return True


def stable_partition(
    sequence: list[str], predicate: Callable[[str], bool]
) -> tuple[list[str], list[str]]:
    true: list[str] = []
    false: list[str] = []
    for item in sequence:
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
