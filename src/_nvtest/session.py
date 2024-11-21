"""Setup and manage the test session"""

import io
import json
import os
import random
import signal
import threading
import time
import traceback
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from functools import partial
from itertools import repeat
from typing import IO
from typing import Any
from typing import Generator
from typing import Type

from . import config
from . import plugin
from .error import FailFast
from .error import StopExecution
from .finder import Finder
from .generator import AbstractTestGenerator
from .queues import BatchResourceQueue
from .queues import Empty as EmptyQueue
from .queues import ResourceQueue
from .queues import factory as q_factory
from .runners import factory as r_factory
from .status import Status
from .test.batch import TestBatch
from .test.case import TestCase
from .test.case import TestMultiCase
from .test.case import from_state as testcase_from_state
from .third_party import color
from .third_party.lock import Lock
from .third_party.lock import LockTransaction
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction
from .util import glyphs
from .util import keyboard
from .util import logging
from .util import parallel
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.misc import partition
from .util.returncode import compute_returncode
from .util.time import hhmmss
from .util.time import timestamp
from .when import when

global_session_lock = threading.Lock()


class ExitCode:
    OK: int = 0
    INTERNAL_ERROR: int = 1
    INTERRUPTED: int = 3
    TIMEOUT: int = 5
    NO_TESTS_COLLECTED: int = 7

    @staticmethod
    def compute(cases: list[TestCase]) -> int:
        return compute_returncode(cases)


class ProgressReporting:
    progress_bar = 0
    verbose = 1

    def __init__(self, level: int = 1) -> None:
        self.level = max(0, min(level, 1))

    def __eq__(self, other) -> bool:
        if isinstance(other, ProgressReporting):
            return self.level == other.level
        else:
            return self.level == other


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

    Internally, the submission script calls ``nvtest`` recursively with instructions to run only
    the cases in the batch.

    Test cases within a batch are (by default) run asynchronously thereby allowing for massive
    speed ups in testing times on HPC resources.

    """

    tagfile = "SESSION.TAG"
    default_worktree = "./TestResults"

    def __init__(self, path: str, mode: str = "r", force: bool = False) -> None:
        if mode not in "arw":
            raise ValueError(f"invalid mode: {mode!r}")
        self.work_tree: str
        if mode == "w":
            path = os.path.abspath(path)
            if force and os.path.exists(path):
                if not os.getenv("NVTEST_MAKE_DOCS"):
                    logging.warning(f"Removing {path}")
                force_remove(path)
            if os.path.exists(path):
                raise DirectoryExistsError(f"{path}: directory exists")
            self.work_tree = path
        else:
            root = self.find_root(path)
            if root is None:
                raise NotASession("not a nvtest session (or any of the parent directories)")
            self.work_tree = root
        self.config_dir = os.path.join(self.work_tree, ".nvtest")
        self.log_dir = os.path.join(self.config_dir, "logs")
        self.mode = mode
        self.search_paths: dict[str, list[str]] = {}
        self.generators: list[AbstractTestGenerator] = list()
        self.cases: list[TestCase] = list()
        self.db = Database(self.config_dir, mode=mode)
        if mode in "ra":
            self.load()
        else:
            self.initialize()
        for hook in plugin.plugins():
            hook.session_initialize(self)

        self.exitstatus = -1
        self.returncode = -1
        self.mode = mode
        self.start = -1.0
        self.finish = -1.0

        os.environ.setdefault("NVTEST_LEVEL", "0")
        config.variables["NVTEST_WORK_TREE"] = self.work_tree
        if mode == "w":
            self.save(ini=True)

    @staticmethod
    def find_root(path: str):
        """Walk up ``path``, looking for a test session root.  The search is stops when the root
        directory is reached"""
        path = os.path.abspath(path)
        while True:
            if os.path.exists(os.path.join(path, Session.tagfile)):
                return os.path.dirname(path)
            elif os.path.exists(os.path.join(path, ".nvtest", Session.tagfile)):
                return path
            path = os.path.dirname(path)
            if path == os.path.sep:
                break
        return None

    def dump_attrs(self, file: IO[Any]) -> None:
        """Dump this session attributes to ``file`` as ``json``"""
        attrs: dict[str, Any] = {}
        for var, value in vars(self).items():
            if var not in ("generators", "cases", "db"):
                attrs[var] = value
        json.dump(attrs, file, indent=2)

    def load_attrs(self, file: IO[Any]) -> None:
        """Load attributes, previously dumped by ``dump_attrs``, from ``file``"""
        attrs = json.load(file)
        for var, value in attrs.items():
            setattr(self, var, value)

    def dump_snapshots(self, file: IO[Any]) -> None:
        """Dump a snapshot of for every case in this session to ``file``"""
        logging.debug("Dumping test case snapshots")
        for case in self.cases:
            self.dump_snapshot(case, file)

    def load_snapshots(self, file: IO[Any]) -> dict[str, dict]:
        """Load snapshots for every case in this session"""
        logging.debug("Loading test case snapshots")
        snapshots: dict[str, dict] = {}
        for line in file:
            snapshot = json.loads(line)
            snapshots[snapshot["id"]] = snapshot
        return snapshots

    def dump_snapshot(self, case: TestCase, file: IO[Any]) -> None:
        """Dump a snapshot of a single case ``case`` to ``file``"""
        snapshot = {
            "id": case.id,
            "start": case.start,
            "finish": case.finish,
            "status": {"value": case.status.value, "details": case.status.details},
            "returncode": case.returncode,
            "dependencies": [dep.id for dep in case.dependencies],
        }
        file.write(json.dumps(snapshot) + "\n")

    def dump_testcases(self, file: IO[Any]) -> None:
        """Dump each case's state in this session to ``file`` in json format"""
        logging.debug("Dumping test cases")
        states: list[dict] = []
        for case in self.cases:
            state = case.getstate()
            props = state["properties"]
            props["dependencies"] = [dep["properties"]["id"] for dep in props["dependencies"]]
            props.pop("work_tree", None)
            states.append(state)
        json.dump(states, file, indent=2)

    def load_testcases(self, file: IO[Any]) -> list[TestCase | TestMultiCase]:
        """Load test cases previously dumpped by ``dump_testcases``.  Dependency resolution is also
        performed
        """
        logging.debug("Loading test cases")
        states = json.load(file)
        ts: TopologicalSorter = TopologicalSorter()
        mapping: dict[str, dict] = {}
        for state in states:
            case_id = state["properties"]["id"]
            ts.add(case_id, *state["properties"]["dependencies"])
            mapping[case_id] = state
        cases: dict[str, TestCase] = {}

        logging.debug("Resolving test case dependencies")
        for case_id in ts.static_order():
            state = mapping[case_id]
            dependency_ids = state["properties"].pop("dependencies", [])
            state["properties"]["work_tree"] = self.work_tree
            case = testcase_from_state(state)
            case.dependencies = [cases[dep_id] for dep_id in dependency_ids]
            cases[case.id] = case
            if not case.mask:
                case.refresh(propagate=False)

        logging.debug("Updating test case state to latest snapshot")
        with self.db.open("snapshots", "r") as record:
            snapshots = self.load_snapshots(record)
        for case in cases.values():
            snapshot = snapshots.get(case.id)
            if snapshot is not None:
                case.update(**snapshot)
        return list(cases.values())

    def dump_testfiles(self, file: IO[Any]) -> None:
        """Dump each test file (test generator) in this session to ``file`` in json format"""
        logging.debug("Dumping test case generators")
        testfiles = [f.getstate() for f in self.generators]
        json.dump(testfiles, file, indent=2)

    def load_testfiles(self, file: IO[Any]) -> list[AbstractTestGenerator]:
        """Load test files (test generators) previously dumped by ``dump_testfiles``"""
        logging.debug("Loading test case generators")
        testfiles = [AbstractTestGenerator.from_state(state) for state in json.load(file)]
        return testfiles

    def load(self) -> None:
        """Load an existing test session:

        * load test files and cases from the database;
        * update test cases based on their latest snapshots;
        * update each test case's dependencies; and
        * set configuration values.

        """
        logging.debug(f"Loading test session in {self.work_tree}")
        if config.session.work_tree != self.work_tree:
            raise RuntimeError(
                f"Configuration failed to load correctly, expected "
                f"config.session.work_tree={self.work_tree!r} but got {config.session.work_tree}"
            )

        with self.db.open("files", "r") as record:
            self.generators = self.load_testfiles(record)

        with self.db.open("cases", "r") as record:
            self.cases = self.load_testcases(record)

        with self.db.open("session", "r") as record:
            self.load_attrs(record)

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
            fh.write("# This file is a results directory tag automatically created by nvtest.\n")
        self.set_config_values()

    def set_config_values(self):
        """Set ``section`` configuration values"""
        config.session.work_tree = self.work_tree

    def save(self, ini: bool = False) -> None:
        """Save session data, excluding data that is stored separately in the database"""
        with self.db.open("session", "w") as record:
            self.dump_attrs(record)
        if ini:
            file = os.path.join(self.config_dir, "config")
            with open(file, "w") as fh:
                config.snapshot(fh)
            with self.db.open("plugin", "w") as record:
                json.dump(plugin.getstate(), record, indent=2)

    def add_search_paths(self, search_paths: dict[str, list[str]] | list[str] | str) -> None:
        """Add paths to this session's search paths

        ``search_paths`` is a list of file system folders that will be searched during the
        :meth:`~Session.discover` phase.  If ``search_paths`` is a mapping, it maps a file system
        folder name to tests within this folder, thereby short-circuiting the discovery phase.
        This form is useful if you know which tests to run.

        """
        if isinstance(search_paths, str):
            search_paths = {search_paths: []}
        if isinstance(search_paths, list):
            search_paths = {path: [] for path in search_paths}
        if self.generators:
            raise ValueError("session is already populated")
        errors = 0
        for root, paths in search_paths.items():
            if not root:
                root = os.getcwd()
            if not os.path.isdir(root):
                errors += 1
                logging.warning(f"{root}: directory does not exist and will not be searched")
            else:
                root = os.path.abspath(root)
                self.search_paths[root] = paths
        if errors:
            logging.warning("one or more search paths does not exist")
        self.save()

    def discover(self, pedantic: bool = True) -> None:
        """Walk each path in the session's search path and collect test files"""
        finder = Finder()
        for root, paths in self.search_paths.items():
            finder.add(root, *paths, tolerant=True)
        for hook in plugin.plugins():
            hook.session_discovery(finder)
        finder.prepare()
        self.generators = finder.discover(pedantic=pedantic)
        with self.db.open("files", "w") as record:
            self.dump_testfiles(record)
        logging.debug(f"Discovered {len(self.generators)} test files")

    def lock(
        self,
        keyword_expr: str | None = None,
        parameter_expr: str | None = None,
        on_options: list[str] | None = None,
        owners: set[str] | None = None,
        env_mods: dict[str, str] | None = None,
        regex: str | None = None,
    ) -> None:
        """Lock test files into concrete (parameterized) test cases

        Args:
          keyword_expr: Used to filter tests by keyword.  E.g., if two test define the keywords
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
        self.cases = Finder.lock_and_filter(
            self.generators,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
            on_options=on_options,
            owners=owners,
            env_mods=env_mods,
            regex=regex,
        )
        cases_to_run = [case for case in self.cases if not case.mask]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        with self.db.open("snapshots", "w") as record:
            self.dump_snapshots(record)
        with self.db.open("cases", "w") as record:
            self.dump_testcases(record)
        logging.debug(f"Collected {len(self.cases)} test cases from {len(self.generators)} files")

    def populate(self, copy_all_resources: bool = False) -> list[TestCase]:
        """Populate the work tree with test case assets and return the list of cases ready to run"""
        logging.debug("Populating test case directories")
        with self.rc_environ():
            with working_dir(self.work_tree):
                self.setup_testcases(copy_all_resources=copy_all_resources)
        return [case for case in self.cases if case.status.satisfies(("pending", "ready"))]

    def setup_testcases(self, copy_all_resources: bool = False) -> None:
        """Setup the test cases and take a snapshot"""
        logging.debug("Setting up test cases")
        cases = [case for case in self.cases if not case.mask]
        ts: TopologicalSorter = TopologicalSorter()
        for case in cases:
            ts.add(case, *case.dependencies)
        ts.prepare()
        errors = 0
        while ts.is_active():
            group = ts.get_ready()
            args = zip(group, repeat(self.work_tree), repeat(copy_all_resources))
            if config.debug:
                for a in args:
                    setup_individual_case(*a)
            else:
                parallel.starmap(setup_individual_case, list(args))
            for case in group:
                # Since setup is run in a multiprocessing pool, the internal
                # state is lost and needs to be updated
                case.refresh()
                assert case.status.satisfies(("skipped", "ready", "pending"))
                if case.work_tree is None:
                    errors += 1
                    logging.error(f"{case}: work_tree not set after setup")
            ts.done(*group)
        with self.db.open("snapshots", "a") as record:
            self.dump_snapshots(record)
        with self.db.open("cases", "w") as record:
            self.dump_testcases(record)
        if errors:
            raise ValueError("Stopping due to previous errors")

    def filter(
        self,
        keyword_expr: str | None = None,
        parameter_expr: str | None = None,
        start: str | None = None,
        case_specs: list[str] | None = None,
        stage: str | None = None,
    ) -> list[TestCase]:
        """Filter test cases (mask test cases that don't meet a specific criteria)

        Args:
          keyword_expr: Include those tests matching this keyword expression
          parameter_expr: Include those tests matching this parameter expression
          start: The starting directory the python session was invoked in
          case_specs: Include those tests matching these specs

        Returns:
          A list of test cases

        """
        explicit_start_path = start is not None
        if start is None:
            start = self.work_tree
        elif not os.path.isabs(start):
            start = os.path.join(self.work_tree, start)
        start = os.path.normpath(start)
        # mask all tests and then later enable based on additional conditions
        for case in self.cases:
            if case.mask:
                continue
            if not case.working_directory.startswith(start):
                case.mask = "Unreachable from start directory"
                continue
            if case_specs is not None:
                if any(case.matches(_) for _ in case_specs):
                    case.status.set("ready")
                else:
                    case.mask = color.colorize("deselected by @*b{testspec expression}")
                continue
            if config.test.cpu_count[1] and case.cpus > config.test.cpu_count[1]:
                n = config.test.cpu_count[1]
                case.mask = f"test requires more than {n} cpus"
                continue
            if config.test.gpu_count[1] and case.gpus > config.test.gpu_count[1]:
                n = config.test.gpu_count[1]
                case.mask = f"test requires more than {n} gpus"
                continue
            when_expr: dict[str, str] = {}
            if parameter_expr:
                when_expr.update({"parameters": parameter_expr})
            if keyword_expr:
                when_expr.update({"keywords": keyword_expr})
            if explicit_start_path and not when_expr:
                case.status.set("ready")
                continue
            if not when_expr:
                if stage is not None:
                    if stage in case.stages:
                        case.status.set("ready" if not case.dependencies else "pending")
                elif case.status.value in ("not_run", "cancelled"):
                    case.status.set("ready" if not case.dependencies else "pending")
            else:
                match = when(
                    when_expr,
                    parameters=case.parameters,
                    keywords=case.keywords + case.implicit_keywords,
                )
                if match:
                    case.status.set("ready" if not case.dependencies else "pending")
                elif case.status != "ready":
                    case.mask = f"deselected due to previous status: {case.status.cname}"
                else:
                    case.mask = color.colorize("deselected by @*b{when expression}")

        cases: list[TestCase] = []
        for case in self.cases:
            if case.status.satisfies(("pending", "ready")):
                for dep in case.dependencies:
                    if not dep.status.satisfies(("pending", "ready", "success", "diff")):
                        case.mask = color.colorize("deselected due to @*b{dependency status}")
                        break
                else:
                    cases.append(case)
        return cases

    def bfilter(self, *, lot_no: int, batch_no: int) -> list[TestCase]:
        """Mask any test cases not in batch number ``batch_no`` from batch lot ``lot_no``"""
        with self.db.open(f"batches/{lot_no}/index", "r") as record:
            batch_info = json.load(record)
        batch_case_ids = batch_info[str(batch_no)]
        expected = len(batch_case_ids)
        logging.info(f"Selecting {expected} tests from batch {lot_no}:{batch_no}")
        for case in self.cases:
            if case.id in batch_case_ids:
                assert not case.mask, case.mask
                if not case.dependencies:
                    case.status.set("ready")
                elif all(_.status.value in ("success", "diff") for _ in case.dependencies):
                    case.status.set("ready")
                elif all(_.id in batch_case_ids for _ in case.dependencies):
                    case.status.set("pending")
                else:
                    failed_deps: list[TestCase] = []
                    case.status.set("pending")
                    for dep in case.dependencies:
                        if dep.status == "success":
                            continue
                        elif dep.status == "ready" and dep.id in batch_case_ids:
                            continue
                        else:
                            failed_deps.append(dep)
                    if failed_deps:
                        logging.warning(
                            f"Not running {case} because the following dependencies failed:"
                        )
                        for dep in failed_deps:
                            logging.emit(f"  - {dep} [id={dep.id}, status={dep.status.value}]\n")
                        case.status.set("not_run", "one or more dependencies failed")
                        case.mask = str(case.status.details)
            else:
                case.mask = f"Case not in batch {lot_no}:{batch_no}"
        return [case for case in self.cases if not case.mask]

    def run(
        self,
        cases: list[TestCase],
        *,
        fail_fast: bool = False,
        reporting: ProgressReporting = ProgressReporting(),
        stage: str | None = None,
    ) -> int:
        """Run each test case in ``cases``.

        Args:
          cases: test cases to run
          fail_fast: If ``True``, stop the execution at the first detected test failure, otherwise
            continuing running until all tests have been run.
          reporting: level of verbosity

        Returns:
          The session returncode (0 for success)

        """
        if not cases:
            raise ValueError("There are no cases to run in this session")
        queue = self.setup_queue(cases)
        config.session.stage = stage = stage or "run"
        config.variables[stage] = stage
        with self.rc_environ():
            with working_dir(self.work_tree):
                cleanup_queue = True
                try:
                    self.start = timestamp()
                    self.finish = -1.0
                    self.process_queue(
                        queue=queue, fail_fast=fail_fast, reporting=reporting, stage=stage
                    )
                except ProcessPoolExecutorFailedToStart:
                    if int(os.getenv("NVTEST_LEVEL", "0")) > 1:
                        # This can happen when the ProcessPoolExecutor fails to obtain a lock.
                        self.returncode = -3
                        for case in queue.cases():
                            case.status.set("retry")
                            case.save()
                    else:
                        self.returncode = compute_returncode(queue.cases())
                    raise
                except KeyboardInterrupt:
                    self.returncode = signal.SIGINT.value
                    cleanup_queue = False
                    raise
                except FailFast as e:
                    name, code = e.args
                    self.returncode = code
                    cleanup_queue = False
                    raise StopExecution(f"fail_fast: {name}", code)
                except Exception:
                    logging.error(traceback.format_exc())
                    self.returncode = compute_returncode(queue.cases())
                    raise
                else:
                    if reporting == ProgressReporting.progress_bar:
                        queue.display_progress(self.start, last=True)
                    self.returncode = compute_returncode(queue.cases())
                finally:
                    queue.close(cleanup=cleanup_queue)
                    self.finish = timestamp()
                for hook in plugin.plugins():
                    hook.session_finish(self)
        self.exitstatus = self.returncode
        self.save()
        return self.returncode

    @contextmanager
    def rc_environ(self, **variables) -> Generator[None, None, None]:
        """Set the runtime environment"""
        save_env = os.environ.copy()
        for var, val in config.variables.items():
            os.environ[var] = val
        os.environ.update(variables)
        level = logging.get_level()
        os.environ["NVTEST_LOG_LEVEL"] = logging.get_level_name(level)
        yield
        os.environ.clear()
        os.environ.update(save_env)

    def process_queue(
        self,
        *,
        queue: ResourceQueue,
        fail_fast: bool,
        reporting: ProgressReporting = ProgressReporting(),
        stage: str,
    ) -> None:
        """Process the test queue, asynchronously

        Args:
          queue: the test queue to process
          fail_fast: If ``True``, stop the execution at the first detected test failure, otherwise
            continuing running until all tests have been run.
          reporting: level of verbosity
          stage: the execution stage

        """
        futures: dict = {}
        duration = lambda: timestamp() - self.start
        timeout = config.session.timeout or -1
        runner = r_factory()
        try:
            with ProcessPoolExecutor(max_workers=queue.workers) as ppe:
                while True:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        logging.emit(queue.status())
                    if reporting == ProgressReporting.progress_bar:
                        queue.display_progress(self.start)
                    if timeout >= 0.0 and duration() > timeout:
                        raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                    try:
                        iid_obj = queue.get()
                        if iid_obj is None:
                            time.sleep(0.01)
                            continue
                        iid, obj = iid_obj
                        self.heartbeat(queue)
                    except EmptyQueue:
                        break
                    future = ppe.submit(
                        runner, obj, verbose=reporting == ProgressReporting.verbose, stage=stage
                    )
                    callback = partial(self.done_callback, iid, queue, fail_fast)
                    future.add_done_callback(callback)
                    futures[iid] = (obj, future)
        except BaseException:
            if ppe is None:
                raise ProcessPoolExecutorFailedToStart
            if ppe._processes:
                for proc in ppe._processes:
                    os.kill(proc, signal.SIGINT)
            ppe.shutdown(wait=True)
            raise

    def heartbeat(self, queue: ResourceQueue) -> None:
        """Take a heartbeat of the simulation by dumping the case, cpu, and gpu IDs that are
        currently busy

        """
        if not config.debug:
            return None
        if isinstance(queue, BatchResourceQueue):
            return None
        hb: dict[str, Any] = {"date": datetime.now().strftime("%c")}
        busy = queue.busy()
        hb["busy"] = [case.id for case in busy]
        hb["busy cpus"] = [cpu_id for case in busy for cpu_id in case.cpu_ids]
        hb["busy gpus"] = [gpu_id for case in busy for gpu_id in case.gpu_ids]
        file: str
        if "NVTEST_LOT_NO" in os.environ:
            lot_no, batch_no = os.environ["NVTEST_LOT_NO"], os.environ["NVTEST_BATCH_NO"]
            file = os.path.join(self.log_dir, f"batches/{lot_no}/hb.{batch_no}.json")
        else:
            file = os.path.join(self.log_dir, "hb.json")
        mkdirp(os.path.dirname(file))
        with open(file, "a") as fh:
            fh.write(json.dumps(hb) + "\n")
        return None

    def done_callback(
        self, iid: int, queue: ResourceQueue, fail_fast: bool, future: Future
    ) -> None:
        """Function registered to the process pool executor to be called when a test (or batch of
        tests) completes

        Args:
          iid: the queue's internal ID of the test (or batch)
          queue: the active test queue
          fail_fast: whether to stop the test session at the first failed test
          future: the future return by the process pool executor

        """
        if future.cancelled():
            return
        try:
            future.result()
        except BrokenProcessPool:
            # The future was probably killed by fail_fast or a keyboard interrupt
            return
        except BrokenPipeError:
            # something bad happened.  On some HPCs we have seen:
            # BrokenPipeError: [Errno 108] Cannot send after transport endpoint shutdown
            # Seems to be a filesystem issue, punt for now
            return

        # The case (or batch) was run in a subprocess.  The object must be
        # refreshed so that the state in this main thread is up to date.

        obj: TestCase | TestBatch = queue.done(iid)
        if not isinstance(obj, (TestBatch, TestCase)):
            logging.error(f"Expected AbstractTestCase, got {obj.__class__.__name__}")
            return
        obj.refresh()
        if isinstance(obj, TestCase):
            with self.db.open("snapshots", "a") as record:
                self.dump_snapshot(obj, record)
            if fail_fast and obj.status != "success":
                code = compute_returncode([obj])
                raise FailFast(str(obj), code)
        else:
            assert isinstance(obj, TestBatch)
            if all(case.status == "retry" for case in obj):
                queue.retry(iid)
                return
            with self.db.open("snapshots") as record:
                snapshots = self.load_snapshots(record)
            for case in obj:
                if case.id not in snapshots:
                    logging.error(f"case ID {case.id} not in batch {obj.batch_no}")
                    continue
                if case.status == "running":
                    # Job was cancelled
                    case.status.set("cancelled", "batch cancelled")
                elif case.status == "skipped":
                    pass
                elif case.status == "ready":
                    case.status.set("skipped", "test skipped for unknown reasons")
                elif case.status != snapshots[case.id]["status"]["value"]:
                    if config.debug:
                        fs = case.status.value
                        ss = snapshots[case.id]["status"]["value"]
                        logging.warning(
                            f"batch {obj.batch_no}, {case}: "
                            f"expected status of future.result to be {ss}, not {fs}"
                        )
                        case.status.set("failed", "unknown failure")
            if fail_fast and any(_.status != "success" for _ in obj):
                code = compute_returncode(obj.cases)
                raise FailFast(str(obj), code)

    def setup_queue(self, cases: list[TestCase]) -> ResourceQueue:
        """Setup the test queue

        Args:
          cases: the test cases to run

        """
        kwds: dict[str, Any] = {}
        queue: ResourceQueue = q_factory(global_session_lock)
        if isinstance(queue, BatchResourceQueue):
            batch_stage = os.path.join(self.config_dir, "batches")
            mkdirp(batch_stage)
            kwds["stage"] = batch_stage
            lot_no = len(os.listdir(batch_stage)) + 1
            kwds["lot_no"] = lot_no
        for case in cases:
            if case.status == "skipped":
                case.save()
            elif not case.status.satisfies(("ready", "pending")):
                raise ValueError(f"{case}: case is not ready or pending")
            elif case.work_tree is None:
                raise ValueError(f"{case}: exec root is not set")
        queue.put(*[case for case in cases if case.status.satisfies(("ready", "pending"))])
        queue.prepare(**kwds)
        if queue.empty():
            raise ValueError("There are no cases to run in this session")
        if isinstance(queue, BatchResourceQueue):
            batches: dict[str, list[str]] = {}
            for batch in queue.queued():
                batches.setdefault(str(batch.batch_no), []).extend([case.id for case in batch])
            with self.db.open(f"batches/{lot_no}/index", "w") as record:
                json.dump(batches, record, indent=2)
            with self.db.open(f"batches/{lot_no}/config", "w") as record:
                json.dump(asdict(config.batch), record, indent=2)
        return queue

    def blogfile(self, batch_no: int, lot_no: int | None) -> str:
        """Get the path of the batch log file"""
        if lot_no is None:
            lot_no = len(os.listdir(os.path.join(self.config_dir, "batches")))  # use latest
        file = os.path.join(self.config_dir, f"batches/{lot_no}/batch.{batch_no}-out.txt")
        return file

    def is_test_case(self, spec: str) -> bool:
        for case in self.cases:
            if case.matches(spec):
                return True
        return False

    @staticmethod
    def overview(cases: list[TestCase]) -> str:
        """Return an overview of the test session"""

        def unreachable(c):
            return c.status == "skipped" and c.status.details.startswith("Unreachable")

        string = io.StringIO()
        files = {case.file for case in cases}
        _, cases = partition(cases, lambda c: unreachable(c))
        fmt = "@*%s{%s} %d test%s from %d file%s\n"
        n, N = len(cases), len(files)
        s, S = "s" if n > 1 else "", "s" if N > 1 else ""
        string.write(color.colorize(fmt % ("c", "collected", n, s, N, S)))
        cases_to_run = [case for case in cases if not case.mask and not case.skipped]
        files = {case.file for case in cases_to_run}
        n, N = len(cases_to_run), len(files)
        s, S = "s" if n > 1 else "", "s" if N > 1 else ""
        string.write(color.colorize(fmt % ("g", "selected", n, s, N, S)))
        skipped = [case for case in cases if case.mask]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            assert case.mask is not None
            skipped_reasons[case.mask] = skipped_reasons.get(case.mask, 0) + 1
        if skipped:
            string.write(color.colorize("@*b{skipping} %d test cases" % len(skipped)) + "\n")
            reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
            for reason in reversed(reasons):
                string.write(f"{glyphs.bullet} {skipped_reasons[reason]} {reason.lstrip()}\n")
        return string.getvalue()

    @staticmethod
    def summary(cases: list[TestCase], include_pass: bool = True) -> str:
        """Return a summary of the completed test cases.  if ``include_pass is True``, include
        passed tests in the summary

        """
        file = io.StringIO()
        if not cases:
            file.write("Nothing to report\n")
            return file.getvalue()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            totals.setdefault(case.status.value, []).append(case)
        for status in Status.members:
            if not include_pass and status == "success":
                continue
            glyph = Status.glyph(status)
            if status in totals:
                for case in sorted(totals[status], key=lambda t: t.name):
                    file.write("%s %s\n" % (glyph, case.describe()))
        string = file.getvalue()
        if string.strip():
            string = color.colorize("@*{Short test summary info}\n") + string + "\n"
        return string

    @staticmethod
    def footer(cases: list[TestCase], duration: float = -1, title="Session done") -> str:
        """Return a short, high-level, summary of test results"""
        string = io.StringIO()
        if duration == -1:
            has_a = any(_.start for _ in cases if _.start > 0)
            has_b = any(_.finish for _ in cases if _.finish > 0)
            if has_a and has_b:
                finish = max(_.finish for _ in cases if _.finish > 0)
                start = min(_.start for _ in cases if _.start > 0)
                duration = finish - start
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            totals.setdefault(case.status.value, []).append(case)
        N = len(cases)
        summary = ["@*b{%d total}" % N]
        for member in Status.colors:
            n = len(totals.get(member, []))
            if n:
                c = Status.colors[member]
                stat = totals[member][0].status.name
                summary.append(color.colorize("@%s{%d %s}" % (c, n, stat.lower())))
        emojis = [glyphs.sparkles, glyphs.collision, glyphs.highvolt]
        x, y = random.sample(emojis, 2)
        kwds = {
            "x": x,
            "y": y,
            "s": ", ".join(summary),
            "t": hhmmss(None if duration < 0 else duration),
            "title": title,
        }
        string.write(color.colorize("%(x)s%(x)s @*{%(title)s} -- %(s)s in @*{%(t)s}\n" % kwds))
        return string.getvalue()

    @staticmethod
    def durations(cases: list[TestCase], N: int) -> str:
        """Return a string describing the ``N`` slowest tests"""
        string = io.StringIO()
        cases = [c for c in cases if c.duration > 0]
        sorted_cases = sorted(cases, key=lambda x: x.duration)
        if N > 0:
            sorted_cases = sorted_cases[-N:]
        kwds = {"t": glyphs.turtle, "N": N}
        string.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
        for case in sorted_cases:
            id = color.colorize("@*b{%s}" % case.id[:7])
            string.write("  %6.2f   %s    %s\n" % (case.duration, id, case.pretty_repr()))
        string.write("\n")
        return string.getvalue()

    @staticmethod
    def status(cases: list[TestCase], show_logs: bool = False, sortby: str = "duration") -> str:
        """Return a string describing the status of each test (grouped by status)"""
        file = io.StringIO()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.mask:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        if "masked" in totals:
            for case in sort_cases_by(totals["masked"], field=sortby):
                description = case.describe(include_logfile_path=show_logs)
                file.write("%s %s\n" % (glyphs.masked, description))
        for member in Status.members:
            if member in totals:
                for case in sort_cases_by(totals[member], field=sortby):
                    glyph = Status.glyph(case.status.value)
                    description = case.describe(include_logfile_path=show_logs)
                    file.write("%s %s\n" % (glyph, description))
        return file.getvalue()

    def report(
        self,
        report_chars: str,
        show_logs: bool = False,
        sortby: str = "durations",
        durations: int | None = None,
        pathspec: str | None = None,
    ) -> str:
        cases: list[TestCase] = self.cases
        cases_to_show: list[TestCase]
        rc = set(report_chars)
        if pathspec is not None:
            if TestCase.spec_like(pathspec):
                cases = [c for c in cases if c.matches(pathspec)]
                rc.add("A")
            else:
                pathspec = os.path.abspath(pathspec)
                if pathspec != self.work_tree:
                    cases = [c for c in cases if c.working_directory.startswith(pathspec)]
        if "A" in rc:
            if "x" in rc:
                cases_to_show = cases
            else:
                cases_to_show = [c for c in cases if not c.mask]
        elif "a" in rc:
            if "x" in rc:
                cases_to_show = [c for c in cases if c.status != "success"]
            else:
                cases_to_show = [c for c in cases if not c.mask and c.status != "success"]
        else:
            cases_to_show = []
            for case in cases:
                if case.mask:
                    if "x" in rc:
                        cases_to_show.append(case)
                elif "s" in rc and case.status == "skipped":
                    cases_to_show.append(case)
                elif "p" in rc and case.status.value in ("success", "xdiff", "xfail"):
                    cases_to_show.append(case)
                elif "f" in rc and case.status == "failed":
                    cases_to_show.append(case)
                elif "d" in rc and case.status == "diffed":
                    cases_to_show.append(case)
                elif "t" in rc and case.status == "timeout":
                    cases_to_show.append(case)
                elif "n" in rc and case.status.value in (
                    "ready",
                    "created",
                    "pending",
                    "cancelled",
                    "not_run",
                ):
                    cases_to_show.append(case)
        file = io.StringIO()
        if cases_to_show:
            file.write(self.status(cases_to_show, show_logs=show_logs, sortby=sortby) + "\n")
        if durations:
            file.write(self.durations(cases_to_show, int(durations)) + "\n")
        file.write(self.footer([c for c in self.cases if not c.mask], title="Summary") + "\n")
        return file.getvalue()


class Database:
    """Manages the test session database

    Args:
        directory: Where to store database assets
        mode: File mode

    """

    def __init__(self, directory: str, mode="a") -> None:
        self.home = os.path.join(os.path.abspath(directory), "objects")
        if mode in "ra":
            if not os.path.exists(self.home):
                raise FileNotFoundError(self.home)
        elif mode == "w":
            force_remove(self.home)
        else:
            raise ValueError(f"{mode!r}: unknown file mode")
        self.lock = Lock(self.join_path("lock"))
        if mode == "w":
            with self.open("DB.TAG", "w") as fh:
                fh.write(datetime.today().strftime("%c"))

    def exists(self, name: str) -> bool:
        return os.path.exists(self.join_path(name))

    def join_path(self, name: str) -> str:
        return os.path.join(self.home, name)

    @contextmanager
    def open(self, name: str, mode: str = "r") -> Generator[IO, None, None]:
        path = self.join_path(name)
        mkdirp(os.path.dirname(path))
        transaction_type: Type[LockTransaction]
        transaction_type = ReadTransaction if mode == "r" else WriteTransaction
        with transaction_type(self.lock):
            with open(path, mode) as fh:
                yield fh


def setup_individual_case(case, work_tree, copy_all_resources):
    """Set up the test case.  This is done in a free function so that it can
    more easily be parallelized in a multiprocessor Pool"""
    logging.debug(f"Setting up {case}")
    case.setup(work_tree, copy_all_resources=copy_all_resources)


def sort_cases_by(cases: list[TestCase], field="duration") -> list[TestCase]:
    if cases and isinstance(getattr(cases[0], field), str):
        return sorted(cases, key=lambda case: getattr(case, field).lower())
    return sorted(cases, key=lambda case: getattr(case, field))


class DirectoryExistsError(Exception):
    pass


class NotASession(Exception):
    pass


class ProcessPoolExecutorFailedToStart(Exception):
    pass
