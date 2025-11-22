# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import hashlib
import os
import pickle  # nosec B403
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator

from . import config
from . import testspec
from . import when
from .generator import AbstractTestGenerator
from .plugins.types import ScanPath
from .session import Session
from .session import SessionResults
from .testcase import TestCase
from .testexec import ExecutionSpace
from .testspec import DraftSpec
from .testspec import ResolvedSpec
from .testspec import TestSpec
from .util import json_helper as json
from .util import logging
from .util.filesystem import atomic_write
from .util.filesystem import force_remove
from .util.filesystem import write_directory_tag
from .util.graph import TopologicalSorter
from .util.graph import reachable_nodes
from .util.graph import static_order
from .util.parallel import starmap

logger = logging.get_logger(__name__)

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
view_tag = "VIEW.TAG"


DB_MAX_RETRIES = 8
DB_BASE_DELAY = 0.05  # 50ms base for exponential backoff (0.05, 0.1, 0.2, ...)


@dataclasses.dataclass
class SpecSelection:
    specs: list[TestSpec]
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

        # Temporary data
        self.tmp_dir: Path

        # Storage for SpecSelection tags
        self.tags_dir: Path

        # Text logs
        self.logs_dir: Path

        # Pointer to latest session
        self.head: Path

        self.lockfile: Path
        self.results_db: Path

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
        self.tmp_dir = self.root / "tmp"
        self.tags_dir = self.root / "tags"
        self.logs_dir = self.root / "logs"
        self.head = self.root / "HEAD"
        self.lockfile = self.root / "lock"
        self.results_db = self.root / "latest.db"
        self._spec_ids = set()

    @staticmethod
    def remove(start: str | Path = Path.cwd()) -> Path | None:
        relpath = Path(start).absolute().relative_to(Path.cwd())
        pm = logger.progress_monitor(f"Removing workspace from {relpath}")
        anchor = Workspace.find_anchor(start=start)
        if anchor is None:
            pm.done("no workspace found")
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
        pm = logger.progress_monitor(f"Initialing empty canary workspace at {path}")
        self: Workspace = object.__new__(cls)
        self.initialize_properties(anchor=path)
        if self.root.exists():
            pm.done("workspace already exists")
            raise WorkspaceExistsError(path)
        self.root.mkdir(parents=True)
        write_directory_tag(self.root / workspace_tag)

        self.casespecs_dir.mkdir(parents=True)
        self.generators_dir.mkdir(parents=True)
        self.refs_dir.mkdir(parents=True)
        self.sessions_dir.mkdir(parents=True)
        self.cache_dir.mkdir(parents=True)
        self.tmp_dir.mkdir(parents=True)
        self.tags_dir.mkdir(parents=True)
        self.tag("default")
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

        WorkspaceResultsDB.create(self.results_db)

        file = self.root / "canary.yaml"
        file.write_text(json.dumps({"canary": {}}))

        file = self.casespecs_dir / "index.json"
        file.write_text(json.dumps({}))

        file = self.casespecs_dir / "graph.json"
        file.write_text(json.dumps({}))

        pm.done("done")

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
        return self

    def sessions(self) -> Generator[Session, None, None]:
        for path in self.sessions_dir.iterdir():
            if Session.is_session(path):
                yield Session.load(path)

    @contextmanager
    def session(
        self, selection: SpecSelection | None = None, name: str | None = None
    ) -> Generator[Session, None, None]:
        session: Session
        if selection is not None and name is not None:
            raise TypeError("Mutually exlusive keyword arguments: 'selection', 'name'")
        elif selection is None and name is None:
            raise TypeError("Missing required keyword arguments: 'selection' or 'name'")
        if selection is not None:
            session = Session.create(self.sessions_dir, selection)
            logger.info(f"Created test session at {session.name}")
        else:
            root = self.sessions_dir / name
            session = Session.load(root)
            logger.info(f"Loaded test session at {session.name}")
        yield session

    def load_latest_results(self) -> dict[str, Any]:
        latest = WorkspaceResultsDB(self.results_db).load_latest_results()
        return latest

    def add_session_results(self, results: SessionResults) -> None:
        """Update latest results, view, and refs with results from ``session``"""
        WorkspaceResultsDB(self.results_db).update_session_results(results)
        view_entries: dict[str, list[str]] = {}
        for case in results.cases:
            relpath = case.workspace.dir.relative_to(results.prefix / "work")
            view_entries.setdefault(results.prefix / "work", []).append(relpath)

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
                view[case.id] = (str(session.work_dir), relpath)
        for path in self.view.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
        view_entries: dict[str, list[str]] = {}
        for root, path in view.values():
            view_entries.setdefault(root, []).append(path)
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
        generator_count = 0
        if (self.generators_dir / "index.json").exists():
            index = json.loads((self.generators_dir / "index.json").read_text())
            generator_count = len(index)
        info = {
            "root": str(self.root),
            "generator_count": generator_count,
            "session_count": len([p for p in self.sessions_dir.glob("*") if p.is_dir()]),
            "latest_session": latest_session,
            "tags": sorted(p.stem for p in self.tags_dir.glob("*")),
            "version": canary.version,
            "workspace_version": (self.root / "VERSION").read_text().strip(),
        }
        return info

    def add_generators(self, generators: list[AbstractTestGenerator]) -> None:
        pm = logger.progress_monitor("@*{Adding} test case generators to workspace")
        file = self.generators_dir / "index.json"
        index: dict[str, Any] = {}
        if file.exists():
            index.update(json.loads(file.read_text()))
        for generator in generators:
            index[generator.id] = generator.getstate()
        file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(file, json.dumps(index, indent=2))
        pm.done()

    def load_testcase_generators(self) -> list[AbstractTestGenerator]:
        """Load test case generators"""
        generators: list[AbstractTestGenerator] = []
        pm = logger.progress_monitor("@*{Loading} test case generators")
        try:
            file = self.generators_dir / "index.json"
            index: dict[str, Any] = {}
            if file.exists():
                index.update(json.loads(file.read_text()))
            for state in index.values():
                generator = AbstractTestGenerator.from_state(state)
                generators.append(generator)
        except Exception:
            status = "failed"
            raise
        else:
            status = "done"
        finally:
            pm.done(status)
        return generators

    def active_testcases(self) -> list[TestCase]:
        return self.load_testcases()

    def add(
        self, scan_paths: dict[str, list[str]], pedantic: bool = True
    ) -> list[AbstractTestGenerator]:
        """Find test case generators in scan_paths and add them to this workspace"""
        generators: list[AbstractTestGenerator] = []
        for root, paths in scan_paths.items():
            fs_root = root if "@" not in root else root.partition("@")[-1]
            pm = logger.progress_monitor(f"@*{{Collecting}} test case generators in {fs_root}")
            p = ScanPath(root=root, paths=paths)
            generators.extend(config.pluginmanager.hook.canary_collect_generators(scan_path=p))
            pm.done()
        self.add_generators(generators)
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
                    selection = pickle.load(fh)  # nosec B301
                    selection.specs = None
                with open(file, "wb") as fh:
                    pickle.dump(selection, fh)
        logger.info(f"@*{{Added}} {len(generators)} new test case generators to {self.root}")
        return generators

    def resolve_root_ids(self, roots: list[str], graph: dict[str, list[str]]) -> None:
        """Expand roots to full IDs.  roots is a spec ID, or partial ID, and can be preceded by /"""

        def find(root: str) -> str:
            sygil = testspec.select_sygil
            if root in graph:
                return root
            for id in graph:
                if id.startswith(root):
                    return id
                elif root.startswith(sygil) and id.startswith(root[1:]):
                    return id
            raise SpecNotFoundError(root)

        for i, root in enumerate(roots):
            roots[i] = find(root)

    def _load_testspecs(self, roots: list[str] | None = None) -> list[ResolvedSpec]:
        """Load cached test specs.  Dependency resolution is performed."""
        index: dict[str, Any] = {}
        ifile = self.casespecs_dir / "index.json"
        if ifile.exists():
            index.update(json.loads(ifile.read_text()))
        graph: dict[str, list[str]] = {}
        gfile = self.casespecs_dir / "graph.json"
        if gfile.exists():
            graph.update(json.loads(gfile.read_text()))
        if roots:
            self.resolve_root_ids(roots, graph)
            reachable = reachable_nodes(graph, roots)
            graph = {id: graph[id] for id in reachable}
        lookup: dict[str, ResolvedSpec] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            file = self.casespecs_dir / str(index[id]["relpath"])
            lock_data = json.loads(file.read_text())
            spec = ResolvedSpec.from_dict(lock_data, lookup)
            lookup[id] = spec
        return list(lookup.values())

    def load_testspecs(self, roots: list[str] | None = None) -> list[ResolvedSpec]:
        """Load cached test specs.  Dependency resolution is performed.

        Args:
          roots: only return specs matching these roots

        Returns:
          Test specs
        """
        specs = self._load_testspecs(roots=roots)
        if roots:
            return [spec for spec in specs if spec.id in roots]
        return specs

    def load_testcases(self, roots: list[str] | None = None) -> list[TestCase]:
        """Load cached test cases.  Dependency resolution is performed.  If ``latest is True``,
        update each case to point to the latest run instance.
        """
        lookup: dict[str, TestCase] = {}
        specs = self._load_testspecs(roots=roots)
        latest = self.load_latest_results()
        for spec in static_order(specs):
            if mine := latest.get(spec.id):
                dependencies = [lookup[dep.id] for dep in spec.dependencies]
                space = ExecutionSpace(
                    root=Path(mine["ws_root"]),
                    path=Path(mine["ws_path"]),
                    session=mine["session"],
                )
                case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
                case.status.set(
                    mine["status"],
                    message=mine["details"] or "",
                    code=mine["exitcode"],
                )
                case.timekeeper.started_on = mine["started_on"] or "NA"
                case.timekeeper.finished_on = mine["finished_on"] or "NA"
                case.timekeeper.duration = mine["duration"]
                lookup[spec.id] = case
        if roots:
            return [case for case in lookup.values() if case.id in roots]
        return list(lookup.values())

    def get_selection_by_specs(self, roots: list[str], tag: str | None = None) -> SpecSelection:
        specs = self.load_testspecs(roots=roots)
        final = testspec.finalize(specs)
        selection = SpecSelection(final, tag)
        if tag is not None:
            self.cache_selection(selection)
        return selection

    def select_from_path(
        self,
        path: Path,
        keyword_exprs: list[str] | None = None,
    ) -> list[TestCase]:
        roots: list[str] = []
        for file in path.rglob("testcase.lock"):
            lock_data = json.loads(file.read_text())
            roots.append(lock_data["spec"]["id"])
        cases = self.load_testcases(roots=roots)
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
        paths: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        on_options: list[str] | None = None,
        regex: str | None = None,
        case_specs: list[str] | None = None,
        **kwargs: Any,
    ) -> list[TestSpec]:
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
        specs: list[ResolvedSpec]
        generators = self.load_testcase_generators()
        if paths:
            relative_to = lambda f1, f2: Path(f1.file).is_relative_to(Path(f2).absolute())
            generators = [g for p in paths for g in generators if relative_to(g, p)]
        meta = {"f": sorted([str(generator.file) for generator in generators]), "o": on_options}
        sha = hashlib.sha256(json.dumps(meta).encode("utf-8")).hexdigest()
        file = self.cache_dir / "lock" / sha[:20]
        if file.exists():
            logger.debug("Reading test specs from cache")
            specs = self.load_testspecs()
        else:
            specs = generate_specs(generators, on_options=on_options)
            # Add all test specs to the object store before masking so that future stages don't
            # inherit this stage's mask (if any)
            self.add_specs(specs)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.touch()

        ids: list[str] | None = None
        if case_specs:
            ids = [_[1:] for _ in case_specs]

        config.pluginmanager.hook.canary_testsuite_mask(
            specs=specs,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            ids=ids,
        )
        final = testspec.finalize(specs)
        config.pluginmanager.hook.canary_collectreport(specs=final)

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
        paths: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: set[str] | None = None,
        on_options: list[str] | None = None,
        case_specs: list[str] | None = None,
        regex: str | None = None,
    ) -> SpecSelection:
        logger.info("@*{Selecting} test cases from generators")
        kwds = dict(
            paths=paths,
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

        selection: SpecSelection

        cache_file = self.cache_dir / "select" / tag
        if not cache_file.exists():
            link = tag_file.read_text().strip()
            meta = json.loads((self.tags_dir / link).read_text())
            specs = self.lock(**meta)
            selection = SpecSelection(specs=specs, tag=tag)
            self.cache_selection(selection)
            return selection

        with open(cache_file, "rb") as fh:
            selection = pickle.load(fh)  # nosec B301

        if selection.specs:
            return selection

        # No cases: cache was invalidated at some point
        link = tag_file.read_text().strip()
        meta = json.loads((self.tags_dir / link).read_text())
        specs = self.lock(**meta)
        selection = SpecSelection(specs=specs, tag=tag_file.name)
        self.cache_selection(selection)
        return selection

    def add_specs(self, specs: list[ResolvedSpec]) -> None:
        index: dict[str, Any] = {}
        ifile = self.casespecs_dir / "index.json"
        if ifile.exists():
            index.update(json.loads(ifile.read_text()))
        graph = {}
        gfile = self.casespecs_dir / "graph.json"
        if gfile.exists():
            graph.update(json.loads(gfile.read_text()))
        timestamp = datetime.datetime.now().timestamp()
        for spec in specs:
            root = hashlib.sha256(str(spec.file_root).encode("utf-8")).hexdigest()[:8]
            file = self.casespecs_dir / root / f"{spec.id}.json"
            file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(file, spec.dumps(indent=2))
            index[spec.id] = {"relpath": file.relative_to(ifile.parent), "generated": timestamp}
            graph[spec.id] = [dep.id for dep in spec.dependencies]
        atomic_write(ifile, json.dumps(index, indent=2))
        atomic_write(gfile, json.dumps(graph, indent=2))

    def statusinfo(self) -> dict[str, list[str]]:
        latest = self.load_latest_results()
        info: dict[str, list[str]] = {}
        specs = {spec.id: spec for spec in self.load_testspecs()}
        for id, entry in latest.items():
            spec = specs[id]
            info.setdefault("id", []).append(spec.id[:7])
            info.setdefault("name", []).append(spec.name)
            info.setdefault("fullname", []).append(spec.fullname)
            info.setdefault("family", []).append(spec.family)
            info.setdefault("file", []).append(spec.file)
            info.setdefault("session", []).append(entry["session"])
            info.setdefault("returncode", []).append(entry["exitcode"])
            info.setdefault("status_name", []).append(entry["status"])
            info.setdefault("status_message", []).append(entry["details"] or "")
            info.setdefault("duration", []).append(entry["duration"])
            info.setdefault("started_on", []).append(entry["started_on"] or "NA")
            info.setdefault("finished_on", []).append(entry["finished_on"] or "NA")
        return info

    def collect_all_testcases(self) -> Generator[TestCase, None, None]:
        for session in self.sessions():
            yield from session.cases

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
                view[case.id] = (str(session.work_dir), relpath)
        try:
            for case in to_remove:
                logger.info(f"gc: removing {case}::{case.workspace.dir}")
                if not dryrun:
                    case.workspace.remove()
        finally:
            logger.info(f"Garbage collected {len(to_remove)} test cases")
            if not dryrun:
                view_entries: dict[str, list[str]] = {}
                for root, path in view.values():
                    view_entries.setdefault(root, []).append(path)
                self.update_view(view_entries)

    def locate(self, *, case: str | None = None) -> Any:
        """Locate something in the workspace"""
        if case is not None:
            return self.locate_testcase(case)

    def locate_testcase(self, root: str) -> TestCase:
        for case in self.load_testcases():
            if case.spec.matches(root):
                return case
        raise ValueError(f"{root}: no matching test found in {self.root}")


def find_generators_in_path(path: str | Path) -> list[AbstractTestGenerator]:
    hook = config.pluginmanager.hook.canary_collect_generators
    generators: list[AbstractTestGenerator] = hook(scan_path=ScanPath(root=str(path)))
    return generators


def generate_specs(
    generators: list["AbstractTestGenerator"],
    on_options: list[str] | None = None,
) -> list[ResolvedSpec]:
    """Generate test cases and filter based on criteria"""
    pm = logger.progress_monitor("@*{Generating} test specs")
    try:
        locked: list[list[DraftSpec]] = []
        if config.get("debug"):
            for f in generators:
                locked.append(lock_file(f, on_options))
        else:
            locked.extend(starmap(lock_file, [(f, on_options) for f in generators]))
        drafts: list[DraftSpec] = []
        for group in locked:
            for spec in group:
                drafts.append(spec)
        nc, ng = len(drafts), len(generators)
    except Exception:
        status = "failed"
        raise
    else:
        status = "done"
    finally:
        pm.done(status)

    duplicates = find_duplicates(drafts)
    if duplicates:
        logger.error("Duplicate test IDs generated for the following test cases")
        for id, dspecs in duplicates.items():
            logger.error(f"{id}:")
            for spec in dspecs:
                logger.log(
                    logging.EMIT, f"  - {spec.display_name}: {spec.file_path}", extra={"prefix": ""}
                )
        raise ValueError("Duplicate test IDs in test suite")

    specs = testspec.resolve(drafts)
    for spec in specs:
        config.pluginmanager.hook.canary_testspec_modify(spec=spec)

    logger.info("@*{Generated} %d test specs from %d generators" % (nc, ng))

    return specs


def lock_file(file: "AbstractTestGenerator", on_options: list[str] | None):
    return file.lock(on_options=on_options)


def find_duplicates(specs: list[DraftSpec]) -> dict[str, list[DraftSpec]]:
    pm = logger.progress_monitor("@*{Searching} for duplicated tests")
    ids = [spec.id for spec in specs]
    duplicate_ids = {id for id in ids if ids.count(id) > 1}
    duplicates: dict[str, list[DraftSpec]] = {}
    for id in duplicate_ids:
        duplicates.setdefault(id, []).extend([_ for _ in specs if _.id == id])
    pm.done()
    return duplicates


class WorkspaceResultsDB:
    """Database wrapper for the "latest results" index."""

    name: str = "LATEST"

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, path: Path) -> "WorkspaceResultsDB":
        """
        Create the 'LATEST' table if it doesn't exist.
        """
        self = cls(path)
        query = f"""CREATE TABLE IF NOT EXISTS {self.name} (
          ID TEXT PRIMARY KEY,
          session TEXT,
          status TEXT,
          exitcode INT,
          details TEXT,
          started_on TEXT,
          finished_on TEXT,
          duration REAL
        );"""
        conn = sqlite3.connect(str(self.path))
        cursor = conn.cursor()
        cursor.execute(query)
        conn.commit()
        conn.close()
        return self

    @classmethod
    def load(cls, path: Path) -> "WorkspaceResultsDB":
        self = cls(path)
        return self

    def add_testcases(self, cases: list[TestCase]):
        batch = []
        for case in cases:
            batch.append(
                {
                    "ID": case.id,
                    "session": None,
                    "status": None,
                    "exitcode": None,
                    "details": None,
                    "started_on": None,
                    "finished_on": None,
                    "duration": None,
                }
            )
        self.safe_write_batch(batch, on_conflict="DO NOTHING")

    def update_session_results(self, results: SessionResults) -> None:
        """Update the 'LATEST' table for a list of completed test cases."""
        batch = []
        format_datetime = lambda x: None if x == "NA" else x
        for case in results.cases:
            batch.append(
                {
                    "ID": case.id,
                    "session": results.session,
                    "status": case.status.name,
                    "exitcode": case.status.code,
                    "details": case.status.message or None,
                    "started_on": format_datetime(case.timekeeper.started_on),
                    "finished_on": format_datetime(case.timekeeper.finished_on),
                    "duration": case.timekeeper.duration,
                    "ws_root": case.workspace.root,
                    "ws_path": case.workspace.path,
                }
            )
        self.safe_write_batch(batch)

    def load_latest_results(self) -> dict[str, dict[str, Any]]:
        """
        Return the full 'LATESTh index as a dictionary keyed by ID.
        """
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {self.name};")
        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description]
        conn.close()
        return {row[0]: {colnames[i]: row[i] for i in range(1, len(colnames))} for row in rows}

    def safe_write_batch(self, batch: list[dict[str, Any]], on_conflict: str | None = None) -> None:
        """
        Write a batch of test-case results inside a single EXCLUSIVE transaction.
        Retries if the SQLite database file is temporarily locked.

        """
        default_conflict_resolution = """DO UPDATE SET
            session = excluded.session,
            status = excluded.status,
            exitcode = excluded.exitcode,
            details = excluded.details,
            started_on = excluded.started_on,
            finished_on= excluded.finished_on,
            duration = excluded.duration"""
        conflict_resolution = on_conflict or default_conflict_resolution
        query = f"""INSERT INTO {self.name}
        (ID,session,status,exitcode,details,started_on,finished_on,duration)
        VALUES (:ID,:session,:status,:exitcode,:details,:started_on,:finished_on,:duration)
        ON CONFLICT(ID) {conflict_resolution}
        WHERE excluded.started_on IS NOT NULL AND (
          latest.started_on IS NULL OR excluded.started_on > latest.started_on
        )"""
        for attempt in range(1, DB_MAX_RETRIES + 1):
            try:
                conn = sqlite3.connect(self.path, timeout=5, isolation_level="EXCLUSIVE")
                cursor = conn.cursor()
                cursor.execute("BEGIN EXCLUSIVE;")  # fast fail if lock can't be acquired
                cursor.executemany(query, batch)
                conn.commit()
                conn.close()
                return  # success!

            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "locked" in msg or "busy" in msg:
                    # Retry with exponential backoff
                    delay = DB_BASE_DELAY * (2 ** (attempt - 1))
                    time.sleep(delay)
                    continue
                raise  # non-lock errors propagate

        raise RuntimeError(f"SQLite write failed after {DB_MAX_RETRIES} retries")


class WorkspaceExistsError(Exception):
    pass


class NotAWorkspaceError(Exception):
    pass


class SpecNotFoundError(Exception):
    pass
