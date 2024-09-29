"""Setup and manage the test session"""

import datetime
import glob
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
from functools import partial
from itertools import repeat
from typing import Any
from typing import Generator
from typing import Optional
from typing import Union

from . import config
from . import plugin
from .database import Database
from .error import FailFast
from .error import StopExecution
from .finder import Finder
from .queues import BatchResourceQueue
from .queues import Empty as EmptyQueue
from .queues import ResourceQueue
from .queues import factory as q_factory
from .resources import ResourceHandler
from .test.batch import Batch
from .test.case import TestCase
from .test.case import dump as dump_testcase
from .test.case import load as load_testcase
from .test.generator import TestGenerator
from .test.generator import getstate as get_testfile_state
from .test.generator import loadstate as load_testfile_state
from .test.status import Status
from .third_party import color
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


class OutputLevel:
    progress_bar = 0
    verbose = 1

    def __init__(self, key: Optional[Union[int, str]] = None):
        self.level: int
        if key is None:
            self.level = self.verbose if config.get("config:debug") else self.progress_bar
        elif isinstance(key, str):
            if key in ("verbose", "v"):
                self.level = self.verbose
            elif key in ("progress_bar", "b"):
                self.level = self.progress_bar
            else:
                raise ValueError(f"{key} not in OutputLevel")
        else:
            if key == 1:
                self.level = self.verbose
            elif key == 0:
                self.level = self.progress_bar
            else:
                raise ValueError(f"{key} not in OutputLevel")

    def __eq__(self, other) -> bool:
        if isinstance(other, OutputLevel):
            return self.level == other.level
        else:
            return self.level == other


class Session:
    """Open the test session and return a corresponding object. If the session cannot be opened, an
    error is raised.

    ``path`` is a path-like object giving the pathname (absolute or relative to the current working
    directory) of the directory to create the test session.

    ``mode`` is an optional string that specifies the mode in which the session is opened. It
    defaults to 'r' which means open for reading. Other values are 'w' for writing (creating a new
    session), and 'a' for appending to an existing session.

    """

    tagfile = "SESSION.TAG"
    default_worktree = "./TestResults"

    def __init__(self, path: str, mode: str = "r", force: bool = False) -> None:
        if mode not in "arw":
            raise ValueError(f"invalid mode: {mode!r}")
        self.root: str
        if mode == "w":
            path = os.path.abspath(path)
            if force and os.path.exists(path):
                if not os.getenv("NVTEST_MAKE_DOCS"):
                    logging.warning(f"Removing {path}")
                force_remove(path)
            if os.path.exists(path):
                raise DirectoryExistsError(f"{path}: directory exists")
            self.root = path
        else:
            root = self.find_root(path)
            if root is None:
                raise NotASession("not a nvtest session (or any of the parent directories)")
            self.root = root
        self.config_dir = os.path.join(self.root, ".nvtest")
        self.log_dir = os.path.join(self.config_dir, "logs")
        os.environ.setdefault("NVTEST_LEVEL", "0")
        os.environ["NVTEST_SESSION_DIR"] = self.root
        os.environ["NVTEST_SESSION_CONFIG_DIR"] = self.config_dir
        self.mode = mode
        self.search_paths: dict[str, list[str]] = {}
        self.generators: list[TestGenerator] = list()
        self.cases: list[TestCase] = list()
        self.db = Database(self.config_dir, mode=mode)
        if mode in "ra":
            self.load()
        else:
            self.initialize()
        for hook in plugin.plugins("session", "setup"):
            hook(self)
        self.exitstatus = -1
        self.returncode = -1
        self.mode = mode
        self.start = -1.0
        self.finish = -1.0

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

    def load_snapshot(self) -> dict[str, dict]:
        snapshots: dict[str, dict] = {}
        with self.db.open("cases/snapshot", "r") as record:
            for line in record:
                snapshot = json.loads(line)
                snapshots[snapshot.get("id")] = snapshot
        return snapshots

    def load(self) -> None:
        """Load an existing test session:

        - load test files and cases from the database;
        - update test cases based on their latest snapshots;
        - update each test case's dependencies; and
        - set configuration values.

        """
        logging.debug(f"Loading test session in {self.root}")
        with open(os.path.join(self.config_dir, "config")) as fh:
            config.load(fh)
        d = self.db.join_path("cases")
        self.cases = [load_testcase(p) for p in glob.glob(os.path.join(d, "*/*"))]
        with self.db.open("files", "r") as record:
            self.generators = [load_testfile_state(state) for state in json.load(record)]
        snapshots = self.load_snapshot()
        for case in self.cases:
            if case.id in snapshots:
                case.restore_snapshot(snapshots[case.id])
        with self.db.open("session", "r") as record:
            data = json.load(record)
        for var, val in data.items():
            setattr(self, var, val)

        ts: TopologicalSorter = TopologicalSorter()
        for case in self.cases:
            ts.add(case, *case.dependencies)
        cases: dict[str, TestCase] = {}
        for case in ts.static_order():
            if case.exec_root is None:
                case.exec_root = self.root
            case.dependencies = [cases[dep.id] for dep in case.dependencies]
            cases[case.id] = case
        self.set_config_values()

    def initialize(self) -> None:
        """Initialize the the test session:

        - create the session's config directory; and
        - save local configuration values to the session configuration scope

        """
        logging.debug(f"Initializing test session in {self.root}")
        file = os.path.join(self.config_dir, self.tagfile)
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a results directory tag automatically created by nvtest.\n")
        self.set_config_values()
        self.save(ini=True)

    def set_config_values(self):
        """Save session configuration data, including copying local configuration data to the
        session scope"""
        config.set("session:root", self.root, scope="session")
        config.set("session:invocation_dir", config.invocation_dir, scope="session")
        config.set("session:start", config.invocation_dir, scope="session")
        attrs = (
            "sockets_per_node",
            "cores_per_socket",
            "cpu_count",
            "gpus_per_socket",
            "gpu_count",
        )
        for attr in attrs:
            value = config.get(f"machine:{attr}", scope="local")
            if value is not None:
                config.set(f"machine:{attr}", value, scope="session")
        for section in ("build", "config", "machine", "option", "variables"):
            # transfer options to the session scope and save it for future sessions
            data = config.get(section, scope="local") or {}
            for key, value in data.items():
                config.set(f"{section}:{key}", value, scope="session")

    def save(self, ini: bool = False) -> None:
        """Save session data, exlcuding data that is stored separately in the database"""
        data: dict[str, Any] = {}
        for var, value in vars(self).items():
            if var not in ("generators", "cases", "db"):
                data[var] = value
        self.db.save_json("session", data)
        if ini:
            self.db.save_json("options", config.get("option"))
            file = os.path.join(self.config_dir, "config")
            with open(file, "w") as fh:
                config.dump(fh)
            self.db.save_json("plugin", plugin.getstate())

    def add_search_paths(self, search_paths: Union[dict[str, list[str]], list[str]]) -> None:
        """Add ``path`` to this session's search paths"""
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

    def discover(self) -> None:
        """Walk each path in the session's search path and collect test files"""
        finder = Finder()
        for root, paths in self.search_paths.items():
            finder.add(root, *paths, tolerant=True)
        for hook in plugin.plugins("session", "discovery"):
            hook(self)
        finder.prepare()
        self.generators = finder.discover()
        files = [get_testfile_state(f) for f in self.generators]
        self.db.save_json("files", files)
        logging.debug(f"Discovered {len(self.generators)} test files")

    def freeze(
        self,
        rh: Optional[ResourceHandler] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        owners: Optional[set[str]] = None,
        env_mods: Optional[dict[str, str]] = None,
    ) -> None:
        """Freeze test files into concrete (parameterized) test cases"""
        self.cases = Finder.freeze(
            self.generators,
            rh=rh,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
            on_options=on_options,
            owners=owners,
            env_mods=env_mods,
        )
        cases_to_run = [case for case in self.cases if not case.mask]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        for case in self.cases:
            with self.db.open(f"cases/{case.id[:2]}/{case.id[2:]}", "w") as fh:
                dump_testcase(case, fh)
        with self.db.open("cases/snapshot", "w") as record:
            for case in self.cases:
                record.write(json.dumps(case.snapshot()) + "\n")
        logging.debug(f"Collected {len(self.cases)} test cases from {len(self.generators)} files")

    def populate(self, copy_all_resources: bool = False) -> None:
        """Populate the work tree with test case assets"""
        logging.debug("Populating test case directories")
        with self.rc_environ():
            with working_dir(self.root):
                self.setup_testcases(copy_all_resources=copy_all_resources)

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
            args = zip(group, repeat(self.root), repeat(copy_all_resources))
            if config.get("config:debug"):
                for a in args:
                    setup_individual_case(*a)
            else:
                parallel.starmap(setup_individual_case, list(args))
            for case in group:
                # Since setup is run in a multiprocessing pool, the internal
                # state is lost and needs to be updated
                case.refresh()
                assert case.status.satisfies(("skipped", "ready", "pending"))
                if case.exec_root is None:
                    errors += 1
                    logging.error(f"{case}: exec_root not set after setup")
            ts.done(*group)
        with self.db.open("cases/snapshot", "a") as record:
            for case in cases:
                record.write(json.dumps(case.snapshot()) + "\n")
        for case in cases:
            with self.db.open(f"cases/{case.id[:2]}/{case.id[2:]}", "w") as fh:
                dump_testcase(case, fh)
        if errors:
            raise ValueError("Stopping due to previous errors")

    def filter(
        self,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        start: Optional[str] = None,
        rh: Optional[ResourceHandler] = None,
        case_specs: Optional[list[str]] = None,
    ) -> list[TestCase]:
        """Filter test cases (mask test cases that don't meet a specific criteria)

        Args:
          keyword_expr: Include those tests matching this keyword expression
          parameter_expr: Include those tests matching this parameter expression
          start: The starting directory the python session was invoked in
          rh: resource handler
          case_specs: Include those tests matching these specs

        Returns:
          A list of test cases

        """
        rh = rh or ResourceHandler()
        explicit_start_path = start is not None
        if start is None:
            start = self.root
        elif not os.path.isabs(start):
            start = os.path.join(self.root, start)
        start = os.path.normpath(start)
        # mask all tests and then later enable based on additional conditions
        for case in self.cases:
            if case.mask:
                continue
            if not case.exec_dir.startswith(start):
                case.mask = "Unreachable from start directory"
                continue
            if case_specs is not None:
                if any(case.matches(_) for _ in case_specs):
                    case.status.set("ready")
                else:
                    case.mask = color.colorize("deselected by @*b{testspec expression}")
                continue
            if rh["test:cpu_count"][1] and case.cpus > rh["test:cpu_count"][1]:
                n = rh["test:cpu_count"][1]
                case.mask = f"test requires more than {n} cpus"
                continue
            if rh["test:gpu_count"][1] and case.gpus > rh["test:gpu_count"][1]:
                n = rh["test:gpu_count"][1]
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
                if case.status.value in ("not_run", "cancelled"):
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
        batch_info = self.db.load_json(f"batches/{lot_no}/index")
        batch_case_ids = batch_info[str(batch_no)]
        for case in self.cases:
            if case.id in batch_case_ids:
                assert not case.mask, case.mask
                if not case.dependencies:
                    case.status.set("ready")
                elif all(_.id in batch_case_ids for _ in case.dependencies):
                    case.status.set("pending")
                elif any([_.status.value not in ("diff", "success") for _ in case.dependencies]):
                    reason = "one or more dependencies failed"
                    case.status.set("skipped", reason)
                    case.save()
                    case.mask = reason
                else:
                    case.status.set("pending")
            else:
                case.mask = f"Case not in batch {lot_no}:{batch_no}"
        return [case for case in self.cases if not case.mask]

    def run(
        self,
        cases: list[TestCase],
        *,
        rh: Optional[ResourceHandler] = None,
        fail_fast: bool = False,
        output: OutputLevel = OutputLevel(),
    ) -> int:
        """Run each test case in ``cases``.

        Args:
          cases: test cases to run
          rh: resource handler, usually set up by the ``nvtest run`` command.
          fail_fast: If ``True``, stop the execution at the first detected test failure, otherwise
            continuing running until all tests have been run.
          output: level of verbosity

        Returns:
          The session returncode (0 for success)

        """
        if not cases:
            raise ValueError("There are no cases to run in this session")
        rh = rh or ResourceHandler()
        queue = self.setup_queue(cases, rh)
        with self.rc_environ():
            with working_dir(self.root):
                cleanup_queue = True
                try:
                    self.start = timestamp()
                    self.finish = -1.0
                    self.process_queue(queue=queue, rh=rh, fail_fast=fail_fast, output=output)
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
                    if output == OutputLevel.progress_bar:
                        queue.display_progress(self.start, last=True)
                    self.returncode = compute_returncode(queue.cases())
                finally:
                    queue.close(cleanup=cleanup_queue)
                    self.finish = timestamp()
                for hook in plugin.plugins("session", "finish"):
                    hook(self)
        self.exitstatus = self.returncode
        self.save()
        return self.returncode

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        """Set the runtime environment"""
        save_env = os.environ.copy()
        variables = config.get("variables") or {}
        for var, val in variables.items():
            os.environ[var] = val
        level = logging.get_level()
        os.environ["NVTEST_LOG_LEVEL"] = logging.get_level_name(level)
        yield
        os.environ.clear()
        os.environ.update(save_env)

    def process_queue(
        self,
        *,
        queue: ResourceQueue,
        rh: ResourceHandler,
        fail_fast: bool,
        output: OutputLevel = OutputLevel(),
    ) -> None:
        """Process the test queue, asynchronously

        Args:
          queue: the test queue to process
          rh: resource handler, usually set up by the ``nvtest run`` command.
          fail_fast: If ``True``, stop the execution at the first detected test failure, otherwise
            continuing running until all tests have been run.
          output: level of verbosity

        """
        futures: dict = {}
        duration = lambda: timestamp() - self.start
        timeout = rh["session:timeout"] or -1
        try:
            with ProcessPoolExecutor(max_workers=queue.workers) as ppe:
                runner_args = []
                runner_kwargs = dict(
                    verbose=output == OutputLevel.verbose, timeoutx=rh["test:timeoutx"]
                )
                if rh["batch:batched"]:
                    runner_args.extend(rh["batch:args"])
                    if rh["batch:workers"]:
                        runner_kwargs["workers"] = rh["batch:workers"]
                while True:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        logging.emit(queue.status())
                    if output == OutputLevel.progress_bar:
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
                    future = ppe.submit(obj, *runner_args, **runner_kwargs)
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
        if not config.get("config:debug"):
            return None
        if isinstance(queue, BatchResourceQueue):
            return None
        hb: dict[str, Any] = {"date": datetime.datetime.now().strftime("%c")}
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

        # The case (or batch) was run in a subprocess.  The object must be
        # refreshed so that the state in this main thread is up to date.

        obj: Union[TestCase, Batch] = queue.done(iid)
        if not isinstance(obj, (Batch, TestCase)):
            logging.error(f"Expected TestCase or Batch, got {obj.__class__.__name__}")
            return
        obj.refresh()

        if isinstance(obj, TestCase):
            with self.db.open(f"cases/{obj.id[:2]}/{obj.id[2:]}", "w") as fh:
                dump_testcase(obj, fh)
            with self.db.open("cases/snapshot", "a") as record:
                record.write(json.dumps(obj.snapshot()) + "\n")
            if fail_fast and obj.status != "success":
                code = compute_returncode([obj])
                raise FailFast(str(obj), code)
        else:
            assert isinstance(obj, Batch)
            if all(case.status == "retry" for case in obj):
                queue.retry(iid)
                return
            snapshots = self.load_snapshot()
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
                    if config.get("config:debug"):
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

    def setup_queue(self, cases: list[TestCase], rh: ResourceHandler) -> ResourceQueue:
        """Setup the test queue

        Args:
          cases: the test cases to run
          rh: resource handler

        """
        kwds: dict[str, Any] = {}
        queue: ResourceQueue = q_factory(rh, global_session_lock)
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
            elif case.exec_root is None:
                raise ValueError(f"{case}: exec root is not set")
        queue.put(*[case for case in cases if case.status.satisfies(("ready", "pending"))])
        queue.prepare(**kwds)
        if queue.empty():
            raise ValueError("There are no cases to run in this session")
        if isinstance(queue, BatchResourceQueue):
            batches: dict[str, list[str]] = {}
            for batch in queue.queued():
                batches.setdefault(str(batch.batch_no), []).extend([case.id for case in batch])
            self.db.save_json(f"batches/{lot_no}/index", batches)
            self.db.save_json(f"batches/{lot_no}/config", rh.data["batch"])
        return queue

    def blogfile(self, batch_no: int, lot_no: Optional[int]) -> str:
        """Get the path of the batch log file"""
        if lot_no is None:
            lot_no = len(os.listdir(os.path.join(self.config_dir, "batches")))  # use latest
        file = os.path.join(self.config_dir, f"batches/{lot_no}/batch.{batch_no}-out.txt")
        return file

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
            string.write("  %6.2f     %s\n" % (case.duration, case.pretty_repr()))
        string.write("\n")
        return string.getvalue()

    @staticmethod
    def status(cases: list[TestCase], show_logs: bool = False, sortby: str = "duration") -> str:
        """Return a string describing the status of each test (grouped by status)"""
        string = io.StringIO()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.mask:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        if "masked" in totals:
            for case in sort_cases_by(totals["masked"], field=sortby):
                description = case.describe(include_logfile_path=show_logs)
                string.write("%s %s\n" % (glyphs.masked, description))
        for member in Status.members:
            if member in totals:
                for case in sort_cases_by(totals[member], field=sortby):
                    glyph = Status.glyph(case.status.value)
                    description = case.describe(include_logfile_path=show_logs)
                    string.write("%s %s\n" % (glyph, description))
        return string.getvalue()


def setup_individual_case(case, exec_root, copy_all_resources):
    """Set up the test case.  This is done in a free function so that it can
    more easily be parallelized in a multiprocessor Pool"""
    logging.debug(f"Setting up {case}")
    case.setup(exec_root, copy_all_resources=copy_all_resources)


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
