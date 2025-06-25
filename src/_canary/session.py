# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Setup and manage the test session"""

import hashlib
import json
import multiprocessing
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import IO
from typing import Any
from typing import Generator

from . import config
from . import finder
from .error import StopExecution
from .generator import AbstractTestGenerator
from .test.batch import TestBatch
from .test.case import TestCase
from .test.case import TestMultiCase
from .test.case import from_state as testcase_from_state
from .third_party.color import colorize
from .third_party.lock import Lock
from .third_party.lock import LockError
from .util import logging
from .util.filesystem import find_work_tree
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.graph import TopologicalSorter
from .util.graph import static_order
from .util.procutils import cleanup_children
from .util.rprobe import cpu_count
from .util.string import pluralize
from .util.time import timestamp

# Session modes are analogous to file modes
session_modes = (
    "w",  # create a new session (write)
    "a",  # open an existing session to modify (append)
    "a+",  # open an existing session to modify, don't reload test cases (lazily loaded as needed)
    "r",  # open an existing session to read (read-only)
    "r+",  # open an existing session to read, don't reload test cases (lazyily-loaded as needed)
)


class Session:
    """Open the test session and return a corresponding object.

    A test "session" is a folder on the filesystem containing assets required to run, analyze, and
    report on a collection of tests.

    ``path`` is a path-like object giving the pathname (absolute or relative to the current working
    directory) of the directory to create the test session.

    ``mode`` is an optional string that specifies the mode in which the session is opened. It
    defaults to ``'r'`` meaning open for reading. Other values are ``'w'`` for writing (creating
    a new session), and ``'a'`` for appending to an existing session.

    If the session cannot be opened, an error is raised.

    In the general case, the steps to creating and running a *new* test session are as follows:

    * Create an instance of :class:`Session` with the root directory and ``mode='w'``.
    * Add search paths to the session.
    * Call :meth:`~Session.discover()` on the session to find test files in search paths.
    * Call :meth:`~Session.lock()` to create test cases from files, filtering cases based on
      criteria passed to ``lock``.
    * Call :meth:`~Session.populate()` to create execution directories for each test case and
      get the list of test cases ready to run
    * Call :meth:`~Session.run(cases)` to run the test cases returned by
      :meth:`~Session.populate`

    The class is designed to support asynchronous processing of test cases so that test cases will
    be run in such a way that maximizes throughput on a given machine.

    .. rubric:: Batched mode

    When running in batch mode, a session is setup and run as normal but when cases are run they
    are first batched into groups and each *batch* is run asynchronously by submitting the batch
    to a scheduler or sub-shell to be ran as follows:

    * Create a test session, discover, lock, populate, and run as in the general case.
    * The run step for batched mode differs from the general case by:
      * putting test cases into batches with other cases requiring the same number of compute nodes;
      * writing a submission (shell) script for the batch that requests the required number of compute nodes; and
      * executing the submission script and waiting for the batch to complete.

    Internally, the submission script calls ``canary`` recursively with instructions to run only
    the cases in the batch.

    Test cases within a batch are (by default) run asynchronously thereby allowing for massive
    speed ups in testing times on HPC resources.

    """

    tagfile = "SESSION.TAG"
    default_worktree = "./TestResults"

    def __init__(self, path: str, mode: str = "r", force: bool = False) -> None:
        if mode not in session_modes:
            raise ValueError(f"invalid mode: {mode!r}")
        self.mode = mode
        self.work_tree: str
        if mode == "w":
            path = os.path.abspath(path)
            if force and os.path.exists(path):
                if not os.getenv("CANARY_MAKE_DOCS"):
                    logging.warning(f"Removing {path}")
                force_remove(path)
            if os.path.exists(path):
                raise DirectoryExistsError(f"{path}: directory exists")
            self.work_tree = path
        else:
            root = find_work_tree(path)
            if root is None:
                raise NotASession("not a canary session (or any of the parent directories)")
            self.work_tree = root
        self.config_dir = os.path.join(self.work_tree, ".canary")
        self.search_paths: dict[str, list[str]] = {}
        self.generators: list[AbstractTestGenerator] = list()
        self.cases: list[TestCase] = list()

        self.exitstatus = -1
        self.returncode = -1
        self.start = -1.0
        self.stop = -1.0

        os.environ.setdefault("CANARY_LEVEL", "0")
        os.environ["CANARY_WORK_TREE"] = self.work_tree
        self.level = int(os.environ["CANARY_LEVEL"])

        self.db = Database(self.config_dir, mode=mode)
        if mode in ("r", "r+", "a", "a+"):
            self.restore_settings()
            self.load_testcase_generators()
            if not mode.endswith("+"):
                self.cases.clear()
                cases = self.load_testcases()
                self.cases.extend(cases)
        else:
            self.initialize()
            config.plugin_manager.hook.canary_session_start(session=self)

        if self.mode == "w":
            self.save(ini=True)

    @classmethod
    def casespecs_view(cls, path: str, case_specs: list[str]) -> "Session":
        """Create a view of this session that only includes cases in ``batch_id``"""
        self = cls(path, mode="a+")
        case_specs.sort()
        with self.db.open("cases/index", "r") as fh:
            index = sorted(json.load(fh)["index"].keys())
        ids: list[str] = []
        for case_spec in case_specs:
            if case_spec.startswith("/"):
                case_spec = case_spec[1:]
            for item in index:
                if item.startswith(case_spec):
                    ids.append(item)
                    break
        self.cases.clear()
        for case in self.load_testcases(ids=ids):
            if case.id not in ids:
                continue
            case.mark_as_ready()
            if not case.status.satisfies(("pending", "ready")):
                logging.error(f"{case}: will not run: {case.status.details}")
            elif case.pending() and not all(dep.id in ids for dep in case.dependencies):
                case.mask = "one or more missing dependencies"
            self.cases.append(case)
        return self

    @classmethod
    def batch_view(cls, path: str, batch_id: str) -> "Session":
        """Create a view of this session that only includes cases in ``batch_id``"""
        ids = TestBatch.loadindex(batch_id)
        if ids is None:
            raise ValueError(f"could not find index for batch {batch_id}")
        expected = len(ids)
        logging.info(f"Selecting {expected} {pluralize('test', expected)} from batch {batch_id}")
        self = cls(path, mode="a+")
        self.cases.clear()
        for case in self.load_testcases(ids=ids):
            if case.id not in ids:
                continue
            case.mark_as_ready()
            if not case.status.satisfies(("pending", "ready")):
                logging.error(f"{case}: will not run: {case.status.details}")
            elif case.pending() and not all(_.id in ids for _ in case.dependencies):
                case.mask = "one or more missing dependencies"
            self.cases.append(case)
        ready = len(self.get_ready())
        logging.info(f"Selected {ready} {pluralize('test', expected)} from batch {batch_id}")
        return self

    def get_ready(self) -> list[TestCase]:
        return [case for case in self.cases if case.ready() or case.pending()]

    def active_cases(self) -> list[TestCase]:
        return [case for case in self.cases if not case.masked()]

    def dump_attrs(self) -> None:
        """Dump this session attributes to ``file`` as ``json``"""
        attrs: dict[str, Any] = {}
        for var, value in vars(self).items():
            if var not in ("generators", "cases", "db", "level"):
                attrs[var] = value
        with self.db.open("session", "w") as file:
            json.dump(attrs, file, indent=2)

    def load_attrs(self) -> None:
        """Load attributes, previously dumped by ``dump_attrs``, from ``file``"""
        with self.db.open("session", "r") as file:
            attrs = json.load(file)
        for var, value in attrs.items():
            if var in ("mode",):
                continue
            setattr(self, var, value)

    def dump_testcases(self) -> None:
        """Dump each case's state in this session to ``file`` in json format"""
        with logging.context(colorize("@*{Generating} test case lockfiles")):
            if len(self.cases) < 100:
                [case.save() for case in self.cases]
            else:
                cpus = cpu_count()
                args = ((case.getstate(), case.lockfile) for case in self.cases)
                pool = multiprocessing.Pool(cpus)
                pool.imap_unordered(json_dump, args, chunksize=len(self.cases) // cpus or 1)
                pool.close()
                pool.join()
            index = {case.id: [dep.id for dep in case.dependencies] for case in self.cases}
            with self.db.open("cases/index", "w") as fh:
                json.dump({"index": index}, fh, indent=2)

    def load_testcases(self, ids: list[str] | None = None) -> list[TestCase]:
        """Load test cases previously dumped by ``dump_testcases``.  Dependency resolution is also
        performed
        """
        ctx = logging.context(colorize("@*{Loading} test cases"), level=logging.DEBUG)
        ctx.start()
        with self.db.open("cases/index", "r") as fh:
            # index format: {ID: [DEPS_IDS]}
            index = json.load(fh)["index"]
        ids_to_load: set[str] = set()
        if ids:
            # we must not only load the requested IDs, but also their dependencies
            for id in ids:
                ids_to_load.add(id)
                ids_to_load.update(index[id])
        ts: TopologicalSorter = TopologicalSorter()
        cases: dict[str, TestCase | TestMultiCase] = {}
        for id, deps in index.items():
            ts.add(id, *deps)
        for id in ts.static_order():
            if ids_to_load and id not in ids_to_load:
                continue
            # see TestCase.lockfile for file pattern
            file = self.db.join_path("cases", id[:2], id[2:], TestCase._lockfile)
            with self.db.open(file) as fh:
                try:
                    state = json.load(fh)
                except json.JSONDecodeError:
                    logging.warning(f"Unable to load {file}!")
                    continue
            state["properties"]["work_tree"] = self.work_tree
            for i, dep_state in enumerate(state["properties"]["dependencies"]):
                # assign dependencies from existing dependencies
                state["properties"]["dependencies"][i] = cases[dep_state["properties"]["id"]]
            cases[id] = testcase_from_state(state)
            assert id == cases[id].id
        ctx.stop()
        return list(cases.values())

    def dump_testcase_generators(self) -> None:
        """Dump each test file (test generator) in this session to ``file`` in json format"""
        logging.debug("Dumping test case generators")
        testfiles = [f.getstate() for f in self.generators]
        with self.db.open("files", mode="w") as file:
            json.dump(testfiles, file, indent=2)

    def load_testcase_generators(self) -> None:
        """Load test files (test generators) previously dumped by ``dump_testcase_generators``"""
        self.generators.clear()
        ctx = logging.context(colorize("@*{Loading} test case generators"), level=logging.DEBUG)
        ctx.start()
        with self.db.open("files", "r") as file:
            states = json.load(file)
            self.generators.extend(map(AbstractTestGenerator.from_state, states))
        ctx.stop()
        return

    def restore_settings(self) -> None:
        """Load an existing test session:

        * load test files and cases from the database;
        * update each test case's dependencies; and
        * set configuration values.

        """
        logging.debug(f"Loading test session in {self.work_tree}")
        if config.session.work_tree is None:
            config.session.work_tree = self.work_tree
        elif not os.path.samefile(config.session.work_tree, self.work_tree):
            msg = "Expected config.session.work_tree=%r but got %s"
            raise RuntimeError(msg % (self.work_tree, config.session.work_tree))
        self.load_attrs()
        self.set_config_values()

    def initialize(self) -> None:
        """Initialize the the test session:

        * create the session's config directory; and
        * save local configuration values to the session configuration scope

        """
        logging.debug(f"Initializing test session in {self.work_tree}")
        file = os.path.join(self.config_dir, self.tagfile)
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a results directory tag automatically created by canary.\n")
        self.set_config_values()

    def set_config_values(self):
        """Set ``section`` configuration values"""
        config.session.work_tree = self.work_tree
        config.session.level = self.level
        config.session.mode = self.mode

    def save(self, ini: bool = False) -> None:
        """Save session data, excluding data that is stored separately in the database"""
        self.dump_attrs()
        if ini:
            file = os.path.join(self.config_dir, "config")
            with open(file, "w") as fh:
                config.snapshot(fh, pretty_print=True)

    def add_search_paths(self, search_paths: dict[str, list[str]] | list[str] | str) -> None:
        """Add paths to this session's search paths

        ``search_paths`` is a list of file system folders that will be searched during the
        :meth:`~Session.discover` phase.  If ``search_paths`` is a mapping, it maps a file system
        folder name to tests within this folder, thereby short-circuiting the discovery phase.
        This form is useful if you know which tests to run.

        """
        if self.generators:
            raise ValueError("session is already populated")
        if isinstance(search_paths, str):
            search_paths = {search_paths: []}
        if isinstance(search_paths, list):
            search_paths = {path: [] for path in search_paths}
        errors = 0
        for root, paths in search_paths.items():
            vcs: str | None = None
            if not root:
                root = os.getcwd()
            if root.startswith(("git@", "repo@")):
                vcs, _, root = root.partition("@")
            if not os.path.isdir(root):
                errors += 1
                logging.warning(f"{root}: directory does not exist and will not be searched")
            else:
                root = os.path.abspath(root)
                if vcs:
                    root = f"{vcs}@{root}"
                self.search_paths[root] = paths
        if errors:
            logging.warning("one or more search paths does not exist")
        self.save()

    def discover(self, pedantic: bool = True) -> None:
        """Walk each path in the session's search path and collect test files"""
        f = finder.Finder()
        for root, paths in self.search_paths.items():
            f.add(root, *paths, tolerant=True)
        f.prepare()
        self.generators = f.discover(pedantic=pedantic)
        self.dump_testcase_generators()
        logging.debug(f"Discovered {len(self.generators)} test files")

    def lock(
        self,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        on_options: list[str] | None = None,
        owners: set[str] | None = None,
        env_mods: dict[str, str] | None = None,
        regex: str | None = None,
    ) -> None:
        """Lock test files into concrete (parameterized) test cases

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
          env_mods: Environment variables to be defined in a tests execution environment.

        """
        cases = finder.generate_test_cases(self.generators, on_options=on_options)
        config.plugin_manager.hook.canary_testsuite_mask(
            cases=cases,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            case_specs=None,
            start=None,
        )
        for case in static_order(cases):
            config.plugin_manager.hook.canary_testcase_modify(case=case)

        self.cases.clear()
        for case in cases:
            if env_mods:
                case.add_default_env(**env_mods)
            if not case.wont_run():
                case.mark_as_ready()
                self.cases.append(case)
        config.plugin_manager.hook.canary_collectreport(cases=cases)
        if not self.get_ready():
            raise StopExecution("No tests to run", 7)

        self.dump_testcases()

    def filter(
        self,
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
        cases = self.active_cases()
        config.plugin_manager.hook.canary_testsuite_mask(
            cases=cases,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            case_specs=case_specs,
            start=start,
        )
        for case in static_order(self.cases):
            config.plugin_manager.hook.canary_testcase_modify(case=case)
        for case in cases:
            if not case.wont_run():
                case.mark_as_ready()
        config.plugin_manager.hook.canary_collectreport(cases=cases)

    def run(self, *, fail_fast: bool = False) -> list[TestCase]:
        """Run each test case in ``cases``.

        Args:
          cases: test cases to run
          fail_fast: If ``True``, stop the execution at the first detected test failure, otherwise
            continuing running until all tests have been run.

        Returns:
          The session returncode (0 for success)

        """
        cases = self.get_ready()
        if not cases:
            raise StopExecution("No tests to run", 7)
        self.start = timestamp()
        rc = config.plugin_manager.hook.canary_runtests(
            session=self, cases=cases, fail_fast=fail_fast
        )
        self.stop = timestamp()
        self.returncode = rc
        self.exitstatus = rc
        config.plugin_manager.hook.canary_session_finish(session=self, exitstatus=self.exitstatus)
        self.save()
        for case in self.cases:
            # we wont run invalid cases, but we want to include them in reports
            if case.status == "invalid":
                cases.append(case)
        return cases


class Database:
    """Manages the test session database

    Args:
        directory: Where to store database assets
        mode: File mode

    """

    def __init__(self, directory: str, mode="a") -> None:
        self.home = os.path.join(os.path.abspath(directory), "objects")
        if mode in ("r", "r+", "a", "a+"):
            if not os.path.exists(self.home):
                raise FileNotFoundError(self.home)
        elif mode == "w":
            force_remove(self.home)
        else:
            raise ValueError(f"{mode!r}: unknown file mode")
        self.lockfile = self.join_path("lock")
        if mode == "w":
            with self.open("DB.TAG", "w") as fh:
                fh.write(datetime.today().strftime("%c"))

    def exists(self, *p: str) -> bool:
        return os.path.exists(self.join_path(*p))

    def join_path(self, *p: str) -> str:
        return os.path.join(self.home, *p)

    @contextmanager
    def read_lock(self, file: str) -> Generator[Lock, None, None]:
        sha1 = hashlib.sha1(file.encode("utf-8")).digest()
        lock_id = prefix_bits(sha1, bit_length(sys.maxsize))
        lock = Lock(
            self.lockfile,
            start=lock_id,
            length=1,
            desc=file,
        )
        lock.acquire_read()
        try:
            yield lock
        except LockError:
            # This addresses the case where a nested lock attempt fails inside
            # of this context manager
            raise
        except (Exception, KeyboardInterrupt):
            lock.release_read()
            raise
        else:
            lock.release_read()

    @contextmanager
    def write_lock(self, file: str) -> Generator[Lock, None, None]:
        sha1 = hashlib.sha1(file.encode("utf-8")).digest()
        lock_id = prefix_bits(sha1, bit_length(sys.maxsize))
        lock = Lock(
            self.lockfile,
            start=lock_id,
            length=1,
            desc=file,
        )
        lock.acquire_write()
        try:
            yield lock
        except LockError:
            # This addresses the case where a nested lock attempt fails inside
            # of this context manager
            raise
        except (Exception, KeyboardInterrupt):
            lock.release_write()
            raise
        else:
            lock.release_write()

    @contextmanager
    def open(self, name: str, mode: str = "r") -> Generator[IO, None, None]:
        path = self.join_path(name)
        mkdirp(os.path.dirname(path))
        if mode == "r":
            with self.read_lock(path):
                with open(path, mode) as fh:
                    yield fh
        else:
            with self.write_lock(path):
                with open(path, mode) as fh:
                    yield fh


def handle_signal(sig, frame):
    cleanup_children()
    raise SystemExit(sig)


def json_dump(args):
    data, filename = args
    mkdirp(os.path.dirname(filename))
    with open(filename, "w") as fh:
        json.dump(data, fh, indent=2)


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


class DirectoryExistsError(Exception):
    pass


class NotASession(Exception):
    pass
