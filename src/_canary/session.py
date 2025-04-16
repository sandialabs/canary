# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Setup and manage the test session"""

import atexit
import hashlib
import io
import json
import multiprocessing
import os
import random
import signal
import sys
import threading
import time
import traceback
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from typing import IO
from typing import Any
from typing import Generator

import psutil

from . import config
from . import finder
from .error import FailFast
from .error import StopExecution
from .generator import AbstractTestGenerator
from .queues import BatchResourceQueue
from .queues import Busy as BusyQueue
from .queues import Empty as EmptyQueue
from .queues import ResourceQueue
from .queues import factory as q_factory
from .runners import factory as r_factory
from .status import Status
from .test.batch import TestBatch
from .test.case import TestCase
from .test.case import TestMultiCase
from .test.case import from_state as testcase_from_state
from .third_party.color import colorize
from .third_party.lock import Lock
from .third_party.lock import LockError
from .util import glyphs
from .util import keyboard
from .util import logging
from .util.compression import compress64
from .util.filesystem import find_work_tree
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.procutils import cleanup_children
from .util.returncode import compute_returncode
from .util.rprobe import cpu_count
from .util.time import hhmmss
from .util.time import timestamp

global_session_lock = threading.Lock()

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
        self.log_dir = os.path.join(self.config_dir, "logs")
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
                self.load_testcases()
        else:
            self.initialize()
            config.plugin_manager.hook.canary_session_start(session=self)

        self.mode = mode

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
        self.load_testcases(ids=ids)
        for case in self.cases:
            if case.pending() and not all(dep.id in ids for dep in case.dependencies):
                case.mask = "one or more missing dependencies"
            else:
                case.mark_as_ready()
        return self

    @classmethod
    def batch_view(cls, path: str, batch_id: str) -> "Session":
        """Create a view of this session that only includes cases in ``batch_id``"""
        batch_case_ids = TestBatch.loadindex(batch_id)
        if batch_case_ids is None:
            raise ValueError(f"could not find index for batch {batch_id}")
        expected = len(batch_case_ids)
        logging.info(f"Selecting {expected} tests from batch {batch_id}")
        self = cls(path, mode="a+")
        self.load_testcases(ids=batch_case_ids)
        for case in self.cases:
            if case.masked():
                logging.warning(f"{case}: unexpected mask: {case.mask}")
            elif case.pending():
                if not all(dep.id in batch_case_ids for dep in case.dependencies):
                    case.mask = "one or more missing dependencies"
        for case in self.cases:
            if not case.masked():
                case.mark_as_ready()
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

    def load_testcases(self, ids: list[str] | None = None) -> None:
        """Load test cases previously dumpped by ``dump_testcases``.  Dependency resolution is also
        performed
        """
        ctx = logging.context(colorize("@*{Loading} test cases"), level=logging.DEBUG)
        ctx.start()
        with self.db.open("cases/index", "r") as fh:
            index = json.load(fh)["index"]
        ids = list(ids or [])
        if ids:
            # Be sure that if an ID is loaded that its dependencies are accessible
            i: int = 0
            while i < len(ids):
                ids.extend(index[ids[i]])
                i += 1
        ts: TopologicalSorter = TopologicalSorter()
        cases: dict[str, TestCase | TestMultiCase] = {}
        for id, deps in index.items():
            ts.add(id, *deps)
        for id in ts.static_order():
            if ids and id not in ids:
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
            case = testcase_from_state(state)
            # update dependencies manually so that the dependencies are consistent across the suite
            for i, dep in enumerate(case.dependencies):
                case.dependencies[i] = cases[dep.id]
            cases[case.id] = case
        ctx.stop()
        self.cases.clear()
        self.cases.extend(cases.values())
        return

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
        self.cases.clear()
        self.cases.extend(finder.generate_test_cases(self.generators, on_options=on_options))
        config.plugin_manager.hook.canary_testsuite_mask(
            cases=self.cases,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            case_specs=None,
            start=None,
        )
        masked: list[TestCase] = []
        for case in self.cases:
            if env_mods:
                case.add_default_env(**env_mods)
            if case.masked() or case.defective():
                masked.append(case)
            else:
                case.mark_as_ready()

        n = len(self.cases) - len(masked)
        logging.info(colorize("@*{Selected} %d test case%s" % (n, "" if n == 1 else "s")))
        if masked:
            self.report_excluded(masked)

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
        masked: list[TestCase] = []
        for case in cases:
            if case.masked() or case.defective():
                masked.append(case)
            else:
                case.mark_as_ready()
        n = len(self.cases) - len(masked)
        logging.info(colorize("@*{Selected} %d test case%s" % (n, "" if n == 1 else "s")))
        if masked:
            self.report_excluded(masked)

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
        atexit.register(cleanup_children)
        queue = self.setup_queue(cases, fail_fast=fail_fast)
        with self.rc_environ():
            with working_dir(self.work_tree):
                cleanup_queue = True
                try:
                    queue_size = len(queue)
                    what = "batches" if isinstance(queue, BatchResourceQueue) else "test cases"
                    logging.info(colorize("@*{Running} %d %s" % (queue_size, what)))
                    self.start = timestamp()
                    self.stop = -1.0
                    logging.debug("Start: processing queue")
                    self.process_queue(queue=queue)
                except ProcessPoolExecutorFailedToStart:
                    if self.level > 0:
                        # This can happen when the ProcessPoolExecutor fails to obtain a lock.
                        self.returncode = -3
                        for case in queue.cases():
                            case.status.set("retry")
                            case.save()
                    else:
                        self.returncode = compute_returncode(queue.cases())
                    raise
                except KeyboardInterrupt:
                    logging.debug("keyboard interrupt: killing child processes and exiting")
                    self.returncode = signal.SIGINT.value
                    cleanup_queue = False
                    raise
                except StopExecution as e:
                    logging.debug("stop execution: killing child processes and exiting")
                    self.returncode = e.exit_code
                except FailFast as e:
                    logging.debug("fail fast: killing child processes and exiting")
                    code = compute_returncode(e.failed)
                    self.returncode = code
                    cleanup_queue = False
                    names = ",".join(_.name for _ in e.failed)
                    raise StopExecution(f"fail_fast: {names}", code)
                except Exception:
                    logging.debug("unknown failure: killing child processes and exiting")
                    logging.error(traceback.format_exc())
                    self.returncode = compute_returncode(queue.cases())
                    raise
                else:
                    if logging.get_level() > logging.INFO:
                        queue.update_progress_bar(self.start, last=True)
                    self.returncode = compute_returncode(queue.cases())
                    self.exitstatus = self.returncode
                    queue.close(cleanup=cleanup_queue)
                    self.stop = timestamp()
                    config.plugin_manager.hook.canary_session_finish(
                        session=self, exitstatus=self.exitstatus
                    )
                    dt = self.stop - self.start
                    msg = colorize("@*{Finished} %d %s (%s)\n" % (queue_size, what, hhmmss(dt)))
                    logging.info(msg)
                    atexit.unregister(cleanup_children)
        self.save()
        for case in self.cases:
            if case.defective():
                cases.append(case)
        return cases

    @contextmanager
    def rc_environ(self, **variables) -> Generator[None, None, None]:
        """Set the runtime environment"""
        save_env = os.environ.copy()
        os.environ.update(variables)
        level = logging.get_level()
        os.environ["CANARY_LOG_LEVEL"] = logging.get_level_name(level)
        yield
        os.environ.clear()
        os.environ.update(save_env)

    def process_queue(self, *, queue: ResourceQueue) -> None:
        """Process the test queue, asynchronously

        Args:
          queue: the test queue to process

        """
        futures: dict = {}
        duration = lambda: timestamp() - self.start
        timeout = float(config.getoption("session_timeout", -1))
        runner = r_factory()
        qsize = queue.qsize
        qrank = 0
        ppe = None
        try:
            with io.StringIO() as fh:
                config.snapshot(fh, pretty_print=False)
                os.environ["CANARYCFG64"] = compress64(fh.getvalue())
            context = multiprocessing.get_context(config.multiprocessing_context)
            with ProcessPoolExecutor(mp_context=context, max_workers=queue.workers) as ppe:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                while True:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        logging.emit(queue.status(start=self.start))
                    if logging.get_level() > logging.INFO:
                        queue.update_progress_bar(self.start)
                    if timeout >= 0.0 and duration() > timeout:
                        raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                    try:
                        iid, obj = queue.get()
                        self.heartbeat(queue)
                    except BusyQueue:
                        time.sleep(0.01)
                        continue
                    except EmptyQueue:
                        break
                    logging.debug(f"Submitting {obj} to process pool for execution", end="... ")
                    future = ppe.submit(runner, obj, qsize=qsize, qrank=qrank)
                    qrank += 1
                    callback = partial(self.done_callback, iid, queue)
                    future.add_done_callback(callback)
                    logging.log(logging.DEBUG, "done")
                    futures[iid] = (obj, future)
        except BaseException:
            if ppe is None:
                raise ProcessPoolExecutorFailedToStart
            raise
        finally:
            if ppe is not None:
                ppe.shutdown(cancel_futures=True)

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
        if "CANARY_BATCH_ID" in os.environ:
            batch_id = os.environ["CANARY_BATCH_ID"]
            file = os.path.join(self.log_dir, f"hb.{batch_id}.json")
        else:
            file = os.path.join(self.log_dir, "hb.json")
        mkdirp(os.path.dirname(file))
        with open(file, "a") as fh:
            fh.write(json.dumps(hb) + "\n")
        return None

    def done_callback(self, iid: int, queue: ResourceQueue, future: Future) -> None:
        """Function registered to the process pool executor to be called when a test (or batch of
        tests) completes

        Args:
          iid: the queue's internal ID of the test (or batch)
          queue: the active test queue
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
        logging.debug(f"Finished {obj} ({obj.duration} s.)")
        if not isinstance(obj, TestCase):
            assert isinstance(obj, TestBatch)
            if all(case.status == "retry" for case in obj):
                queue.retry(iid)
                return
            for case in obj:
                if case.status == "running":
                    # Job was cancelled
                    case.status.set("cancelled", "batch cancelled")
                elif case.status == "skipped":
                    pass
                elif case.status == "ready":
                    case.status.set("not_run", "test not run for unknown reasons")
                elif case.start > 0 and case.stop < 0:
                    case.status.set("cancelled", "test case cancelled")

    def setup_queue(self, cases: list[TestCase], fail_fast: bool = False) -> ResourceQueue:
        """Setup the test queue

        Args:
          cases: the test cases to run

        """
        kwds: dict[str, Any] = {}
        queue: ResourceQueue = q_factory(global_session_lock, fail_fast=fail_fast)
        for case in cases:
            if case.status == "skipped":
                case.save()
            elif not case.status.satisfies(("ready", "pending")):
                raise ValueError(f"{case}: case is not ready or pending")
            # elif case.work_tree is None:
            #    raise ValueError(f"{case}: exec root is not set")
        queue.put(*[case for case in cases if case.status.satisfies(("ready", "pending"))])
        queue.prepare(**kwds)
        if queue.empty():
            raise ValueError("There are no cases to run in this session")
        if isinstance(queue, BatchResourceQueue):
            for batch in queue.queued():
                batch.save()
        return queue

    def batch_logfile(self, batch_id: str) -> str:
        """Get the path of the batch log file"""
        path = TestBatch.logfile(batch_id)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return path

    def is_test_case(self, spec: str) -> bool:
        for case in self.cases:
            if case.matches(spec):
                return True
        return False

    def summary(self, cases: list[TestCase] | None = None, include_pass: bool = True) -> str:
        """Return a summary of the completed test cases.  if ``include_pass is True``, include
        passed tests in the summary

        """
        cases = cases or self.active_cases()
        file = io.StringIO()
        if not cases:
            file.write("Nothing to report\n")
            return file.getvalue()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.defective():
                totals.setdefault("defective", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        if "defective" in totals:
            for case in sorted(totals["defective"], key=lambda t: t.name):
                description = case.describe()
                file.write("%s %s\n" % (glyphs.ballotx, description))
        for status in Status.members:
            if not include_pass and status == "success":
                continue
            glyph = Status.glyph(status)
            if status in totals:
                for case in sorted(totals[status], key=lambda t: t.name):
                    file.write("%s %s\n" % (glyph, case.describe()))
        string = file.getvalue()
        if string.strip():
            string = colorize("@*{Short test summary info}\n") + string + "\n"
        return string

    def footer(
        self, cases: list[TestCase] | None = None, duration: float = -1, title="Session done"
    ) -> str:
        """Return a short, high-level, summary of test results"""
        cases = cases or self.active_cases()
        string = io.StringIO()
        if duration == -1:
            has_a = any(_.start for _ in cases if _.start > 0)
            has_b = any(_.stop for _ in cases if _.stop > 0)
            if has_a and has_b:
                finish = max(_.stop for _ in cases if _.stop > 0)
                start = min(_.start for _ in cases if _.start > 0)
                duration = finish - start
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.defective():
                totals.setdefault("defective", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        N = len(cases)
        summary = ["@*b{%d total}" % N]
        for member in Status.colors:
            n = len(totals.get(member, []))
            if n:
                c = Status.colors[member]
                stat = totals[member][0].status.name
                summary.append(colorize("@%s{%d %s}" % (c, n, stat.lower())))
        if "defective" in totals:
            n = len(totals["defective"])
            summary.append(colorize("@*r{%d defective}" % n))
        emojis = [glyphs.sparkles, glyphs.collision, glyphs.highvolt]
        x, y = random.sample(emojis, 2)
        kwds = {
            "x": x,
            "y": y,
            "s": ", ".join(summary),
            "t": hhmmss(None if duration < 0 else duration),
            "title": title,
        }
        string.write(colorize("%(x)s%(x)s @*{%(title)s} -- %(s)s in @*{%(t)s}\n" % kwds))
        return string.getvalue()

    def durations(self, cases: list[TestCase] | None = None, N: int = 10) -> str:
        """Return a string describing the ``N`` slowest tests"""
        cases = cases or self.active_cases()
        string = io.StringIO()
        cases = [c for c in cases if c.duration > 0]
        sorted_cases = sorted(cases, key=lambda x: x.duration)
        if N > 0:
            sorted_cases = sorted_cases[-N:]
        kwds = {"t": glyphs.turtle, "N": N}
        string.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
        for case in sorted_cases:
            id = colorize("@*b{%s}" % case.id[:7])
            string.write("  %6.2f   %s    %s\n" % (case.duration, id, case.pretty_repr()))
        string.write("\n")
        return string.getvalue()

    def status(self, cases: list[TestCase] | None = None, sortby: str = "duration") -> str:
        """Return a string describing the status of each test (grouped by status)"""
        cases = cases or self.active_cases()
        file = io.StringIO()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.masked():
                totals.setdefault("masked", []).append(case)
            elif case.defective():
                totals.setdefault("defective", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        if "masked" in totals:
            for case in sort_cases_by(totals["masked"], field=sortby):
                description = case.describe()
                file.write("%s %s\n" % (glyphs.masked, description))
        if "defective" in totals:
            for case in sort_cases_by(totals["defective"], field=sortby):
                description = case.describe()
                glyph = colorize("@*r{%s}" % glyphs.ballotx)
                file.write("%s %s\n" % (glyph, description))
        for member in Status.members:
            if member in totals:
                for case in sort_cases_by(totals[member], field=sortby):
                    glyph = Status.glyph(case.status.value)
                    description = case.describe()
                    file.write("%s %s\n" % (glyph, description))
        return file.getvalue()

    @staticmethod
    def report_excluded(excluded_cases: list[TestCase]) -> None:
        n = len(excluded_cases)
        logging.info(colorize("@*{Excluding} %d test cases for the following reasons:" % n))
        reasons: dict[str | None, int] = {}
        for case in excluded_cases:
            if case.masked():
                reasons[case.mask] = reasons.get(case.mask, 0) + 1
            elif case.defective():
                reasons[case.defect] = reasons.get(case.defect, 0) + 1
        keys = sorted(reasons, key=lambda x: reasons[x])
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            logging.emit(f"{3 * glyphs.bullet} {reasons[key]}: {reason}\n")

    def report(
        self,
        report_chars: str,
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
                cases_to_show = [c for c in cases if not c.masked()]
        elif "a" in rc:
            if "x" in rc:
                cases_to_show = [c for c in cases if c.status != "success"]
            else:
                cases_to_show = [c for c in cases if not c.masked() and c.status != "success"]
        else:
            cases_to_show = []
            for case in cases:
                if case.masked():
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
                elif "n" in rc and case.defective():
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
            file.write(self.status(cases=cases_to_show, sortby=sortby) + "\n")
        if durations:
            file.write(self.durations(cases=cases_to_show, N=int(durations)) + "\n")
        s = self.footer(cases=cases_to_show, title="Summary")
        file.write(s + "\n")
        return file.getvalue()


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


def sort_cases_by(cases: list[TestCase], field="duration") -> list[TestCase]:
    if cases and isinstance(getattr(cases[0], field), str):
        return sorted(cases, key=lambda case: getattr(case, field).lower())
    return sorted(cases, key=lambda case: getattr(case, field))


def is_base_process(process: psutil.Process) -> bool:
    """Check if process is one of the resource tracking processes launched by the
    ProcessPoolExecutor"""
    try:
        command = " ".join(process.cmdline())
    except Exception:
        return False
    else:
        return f"{sys.executable} -c from multiprocessing" in command


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


class ProcessPoolExecutorFailedToStart(Exception):
    pass
