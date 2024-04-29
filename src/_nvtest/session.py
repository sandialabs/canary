import glob
import inspect
import json
import os
import pickle
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
from . import directives
from . import plugin
from .error import FailFast
from .error import StopExecution
from .finder import Finder
from .queues import BatchResourceQueue
from .queues import DirectResourceQueue
from .queues import Empty as EmptyQueue
from .queues import ResourceQueue
from .test.batch import Batch
from .test.batch import factory as b_factory
from .test.case import TestCase
from .test.status import Status
from .third_party.color import clen
from .third_party.color import colorize
from .third_party.lock import Lock
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction
from .util import keyboard
from .util import logging
from .util import parallel
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.misc import dedup
from .util.misc import partition
from .util.partition import partition_n
from .util.partition import partition_t
from .util.progress import progress
from .util.returncode import compute_returncode
from .util.time import hhmmss

default_batchsize = 30 * 60  # 30 minutes
default_timeout = 60 * 60  # 60 minutes
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


class Database:
    """Manages the test session database

    Writes an index file containing information about all tests found during
    discovery (index/cases) and a results file for tests that are run
    (stage/cases).  The results file is updated after the completion of each
    test case.

    Reads and writes to the results file are locked to allow running tests in parallel

    Args:
        directory: Where to store database assets
        cases: The list of test cases

    """

    def __init__(self, directory: str, cases: Optional[list[TestCase]] = None) -> None:
        self.directory = os.path.abspath(directory)
        lock_path = os.path.join(self.directory, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session.database")
        if cases is not None:
            self.makeindex(cases)
        elif not os.path.exists(os.path.join(self.directory, "index/cases")):
            raise ValueError(f"index not found at {self.directory}")

    def _single_case_entry(self, case: TestCase) -> dict:
        entry = {
            "start": case.start,
            "finish": case.finish,
            "status": case.status,
            "returncode": case.returncode,
            "dependencies": case.dependencies,
        }
        return entry

    def update(self, cases: Union[TestCase, list[TestCase]]) -> None:
        """Add test case results to the database

        Args:
            cases: list of test cases to add to the database

        """
        if not isinstance(cases, list):
            cases = [cases]
        file = os.path.join(self.directory, "stage/cases")
        mkdirp(os.path.dirname(file))
        with WriteTransaction(self.lock):
            with open(file, "ab") as fh:
                for case in cases:
                    cd = self._single_case_entry(case)
                    pickle.dump({case.id: cd}, fh)

    def load(self) -> list[TestCase]:
        """Load the test results

        Returns:
            The list of ``TestCase``s

        """
        fd: dict[str, TestCase]
        with ReadTransaction(self.lock):
            file = os.path.join(self.directory, "index/cases")
            with open(file, "rb") as fh:
                fd = pickle.load(fh)
            file = os.path.join(self.directory, "stage/cases")
            with open(file, "rb") as fh:
                while True:
                    try:
                        cd = pickle.load(fh)
                    except EOFError:
                        break
                    else:
                        for case_id, value in cd.items():
                            fd[case_id].update(value)
        ts: TopologicalSorter = TopologicalSorter()
        for case in fd.values():
            ts.add(case, *case.dependencies)
        cases: dict[str, TestCase] = {}
        for case in ts.static_order():
            if case.exec_root is None:
                case.exec_root = os.path.dirname(self.directory)
            case.dependencies = [cases[dep.id] for dep in case.dependencies]
            cases[case.id] = case
        return list(cases.values())

    def read(self) -> dict[str, dict]:
        """Read the results file and return a dictionary of the stored ``TestCase`` attributions"""
        with ReadTransaction(self.lock):
            fd: dict[str, dict] = {}
            with open(os.path.join(self.directory, "stage/cases"), "rb") as fh:
                while True:
                    try:
                        cd = pickle.load(fh)
                    except EOFError:
                        break
                    else:
                        for case_id, value in cd.items():
                            fd.setdefault(case_id, {}).update(value)
        return fd

    def makeindex(self, cases: list[TestCase]) -> None:
        """Store each ``TestCase`` in ``cases`` as a dictionary in the index file"""
        files: dict[str, set[str]] = {}
        indexed: dict[str, TestCase] = {}
        for case in cases:
            files.setdefault(case.file_root, set()).add(case.file_path)
            indexed[case.id] = case
        file = os.path.join(self.directory, "index/files")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            json.dump({k: list(v) for (k, v) in files.items()}, fh, indent=2)
        file = os.path.join(self.directory, "index/cases")
        with open(file, "wb") as fh:
            pickle.dump(indexed, fh)
        file = os.path.join(self.directory, "stage/cases")
        mkdirp(os.path.dirname(file))
        with open(file, "wb") as fh:
            for case in cases:
                if case.masked:
                    continue
                cd = self._single_case_entry(case)
                pickle.dump({case.id: cd}, fh)


class Session:
    """Manages the test session

    This object should not be directly instantiated but should be instantiated
    through one of the two factory methods: ``Session.create`` and
    ``Session.load``

    """

    default_work_tree = "./TestResults"
    mode: str
    id: int
    startdir: str
    exitstatus: int
    _work_tree: str
    _avail_cpus: int
    _avail_devices: int
    _avail_cpus_per_test: int
    _avail_devices_per_test: int
    _avail_workers: int
    search_paths: dict[str, list[str]]
    cases: list[TestCase]
    queue: ResourceQueue
    lock: Lock
    db: Database
    ini_options: dict

    def __init__(self) -> None:
        stack = inspect.stack()
        frame = stack[1][0]
        calling_func = None
        if "cls" in frame.f_locals:
            calling_func = getattr(frame.f_locals["cls"], frame.f_code.co_name, None)
        if calling_func not in (Session.create, Session.load):
            raise ValueError("Session must be created through one of its factory methods")
        self.state: int = 0

        nodes = config.get("machine:nodes") or 1
        spn = config.get("machine:sockets_per_node")
        cps = config.get("machine:cores_per_socket")
        cores_per_node = spn * cps
        avail_cpus = nodes * cores_per_node

        self._avail_cpus = avail_cpus
        self._avail_cpus_per_test = self.avail_cpus
        self._avail_workers = config.get("machine:cpu_count")
        self._avail_devices = config.get("machine:device_count")
        self._avail_devices_per_test = self.avail_devices

    @property
    def active_cases(self) -> list[TestCase]:
        return [case for case in self.cases if not case.masked]

    @property
    def work_tree(self) -> str:
        return self._work_tree

    @work_tree.setter
    def work_tree(self, arg: str) -> None:
        self._work_tree = arg

    @property
    def dotdir(self) -> str:
        path = os.path.join(self.work_tree, ".nvtest")
        return path

    @property
    def stage(self) -> str:
        return os.path.join(self.dotdir, "stage")

    @property
    def avail_cpus(self) -> int:
        return self._avail_cpus

    @avail_cpus.setter
    def avail_cpus(self, arg: int) -> None:
        nodes = config.get("machine:nodes") or 1
        spn = config.get("machine:sockets_per_node") or 1
        cps = config.get("machine:cores_per_socket") or config.get("machine:cpu_count")
        cores_per_node = spn * cps
        avail_cpus = nodes * cores_per_node
        if arg > avail_cpus:
            raise ValueError(f"avail_cpus={arg} cannot exceed cpu_count={avail_cpus}")
        self._avail_cpus = arg
        if arg < self._avail_cpus_per_test:
            self._avail_cpus_per_test = arg

    @property
    def avail_cpus_per_test(self) -> int:
        return self._avail_cpus_per_test

    @avail_cpus_per_test.setter
    def avail_cpus_per_test(self, arg: int) -> None:
        if arg > self.avail_cpus:
            n = self.avail_cpus
            raise ValueError(f"avail_cpus_per_test={arg} cannot exceed avail_cpus={n}")
        self._avail_cpus_per_test = arg

    @property
    def avail_devices(self) -> int:
        return self._avail_devices

    @avail_devices.setter
    def avail_devices(self, arg: int) -> None:
        if arg > config.get("machine:device_count"):
            n = config.get("machine:device_count")
            raise ValueError(f"avail_devices={arg} cannot exceed device_count={n}")
        self._avail_devices = arg

    @property
    def avail_devices_per_test(self) -> int:
        return self._avail_devices_per_test

    @avail_devices_per_test.setter
    def avail_devices_per_test(self, arg: int) -> None:
        if arg > self.avail_devices:
            n = self.avail_devices
            raise ValueError(f"avail_devices_per_test={arg} cannot exceed avail_devices={n}")
        self._avail_devices_per_test = arg

    @property
    def avail_workers(self) -> int:
        return self._avail_workers

    @avail_workers.setter
    def avail_workers(self, arg: int) -> None:
        if arg > self.avail_cpus:
            n = self.avail_cpus
            raise ValueError(f"avail_workers={arg} cannot exceed avail_cpus={n}")
        self._avail_workers = arg

    @classmethod
    def create(
        cls,
        *,
        work_tree: str,
        search_paths: dict[str, list[str]],
        avail_cpus: Optional[int] = None,
        avail_cpus_per_test: Optional[int] = None,
        avail_devices: Optional[int] = None,
        avail_devices_per_test: Optional[int] = None,
        avail_workers: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        test_timelimit: Optional[float] = None,
        timeout_multiplier: float = 1.0,
    ) -> "Session":
        if config.has_scope("session"):
            raise ValueError("cannot create new session when another session is active")
        self = cls()
        self.mode = "w"
        self.exitstatus = -1

        logging.debug(f"Creating new test session in {work_tree}")

        try:
            self.initialize(
                work_tree,
                search_paths=search_paths,
                avail_cpus=avail_cpus,
                avail_cpus_per_test=avail_cpus_per_test,
                avail_devices=avail_devices,
                avail_devices_per_test=avail_devices_per_test,
                avail_workers=avail_workers,
                keyword_expr=keyword_expr,
                on_options=on_options,
                parameter_expr=parameter_expr,
            )
        except DirectoryExistsError:
            raise
        except Exception:
            force_remove(self.work_tree)
            raise

        self.populate(
            on_options=on_options,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
            test_timelimit=test_timelimit,
            timeout_multiplier=timeout_multiplier,
        )

        self.ini_options = dict(
            keyword_expr=keyword_expr,
            on_options=on_options,
            parameter_expr=parameter_expr,
            timeout_multiplier=timeout_multiplier,
        )
        self.state = 1

        return self

    def setup(
        self,
        copy_all_resources: bool = False,
        workers_per_batch: Optional[int] = None,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
        scheduler: Optional[str] = None,
        scheduler_options: Optional[list[str]] = None,
    ) -> None:
        if self.state != 1:
            raise ValueError(f"Expected state == 1 (got {self.state})")

        logging.debug("Setting up work tree")
        t_start = time.monotonic()
        self.setup_testcases(self.active_cases, copy_all_resources=copy_all_resources)
        duration = time.monotonic() - t_start

        for hook in plugin.plugins("session", "setup"):
            hook(self)

        self.ini_options.update(
            {
                "batch_count": batch_count,
                "batch_time": batch_time,
                "scheduler": scheduler,
                "scheduler_options": scheduler_options,
                "copy_all_resources": copy_all_resources,
            }
        )
        file = os.path.join(self.dotdir, "params")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            variables = dict(vars(self))
            for attr in ("cases", "queue", "db", "lock"):
                variables.pop(attr, None)
            json.dump(variables, fh, indent=2)

        self.setup_queue(
            batch_count=batch_count,
            batch_time=batch_time,
            scheduler=scheduler,
            scheduler_options=scheduler_options,
            workers_per_batch=workers_per_batch,
        )

        duration = time.monotonic() - t_start
        logging.debug(f"Done setting up work tree ({duration:.2f}s.)")

        self.state = 2

    @classmethod
    def load(cls, *, mode: str = "r") -> "Session":
        if mode not in "ra":
            raise ValueError(f"Incorrect mode {mode!r}")
        self = cls()
        self.work_tree = config.get("session:work_tree")
        logging.info(f"Loading session from {self.work_tree}")
        if not self.work_tree:
            raise ValueError("not a nvtest session (or any of the parent directories): .nvtest")
        self.mode = mode
        self.exitstatus = -1
        assert os.path.exists(self.stage)
        with open(os.path.join(self.dotdir, "params")) as fh:
            for attr, value in json.load(fh).items():
                setattr(self, attr, value)
        self.db = Database(self.dotdir)
        self.cases = self.db.load()
        self.state = 1
        self.mode = mode

        logging.info(f"Available cpus: {self.avail_cpus}")
        logging.info(f"Available cpus per test: {self.avail_cpus_per_test}")
        if self.avail_devices:
            logging.info(f"Available devices: {self.avail_devices}")
            logging.info(f"Available devices per test: {self.avail_devices_per_test}")
        logging.info(f"Maximum number of asynchronous jobs: {self.avail_workers}")

        return self

    def initialize(
        self,
        work_tree: str,
        search_paths: dict[str, list[str]],
        avail_cpus: Optional[int] = None,
        avail_cpus_per_test: Optional[int] = None,
        avail_devices: Optional[int] = None,
        avail_devices_per_test: Optional[int] = None,
        avail_workers: Optional[int] = None,
        **kwds: Any,
    ) -> None:
        """Create the work tree and auxiliary directories, and setup session
        configuration

        """
        self.work_tree = os.path.abspath(work_tree)
        if os.path.exists(self.work_tree):
            raise DirectoryExistsError(f"{self.work_tree}: directory exists")
        mkdirp(self.work_tree)

        t_start = time.monotonic()
        logging.debug("Initializing session")
        if avail_cpus is not None:
            self.avail_cpus = avail_cpus
        if avail_cpus_per_test is not None:
            self.avail_cpus_per_test = avail_cpus_per_test

        if avail_devices is not None:
            self.avail_devices = avail_devices
        if avail_devices_per_test is not None:
            self.avail_devices_per_test = avail_devices_per_test

        if avail_workers is not None:
            self.avail_workers = avail_workers

        self.search_paths = search_paths

        config.set("session:work_tree", self.work_tree, scope="session")
        config.set("session:invocation_dir", config.invocation_dir, scope="session")
        start = os.path.relpath(self.work_tree, os.getcwd()) or "."
        config.set("session:start", start, scope="session")
        for key, value in kwds.items():
            config.set(f"session:{key}", value, scope="session")
        for attr in ("sockets_per_node", "cores_per_socket", "cpu_count"):
            value = config.get(f"machine:{attr}", scope="local")
            if value is not None:
                config.set(f"machine:{attr}", value, scope="session")
        for section in ("build", "config", "machine", "option", "variables"):
            # transfer options to the session scope and save it for future sessions
            data = config.get(section, scope="local") or {}
            for key, value in data.items():
                config.set(f"{section}:{key}", value, scope="session")
        file = os.path.join(self.work_tree, config.config_dir, "config")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            config.dump(fh, scope="session")
        duration = time.monotonic() - t_start
        logging.debug(f"Done initializing session ({duration:.2f}s.)")

    def populate(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        test_timelimit: Optional[float] = None,
        timeout_multiplier: float = 1.0,
    ) -> None:
        if self.mode != "w":
            raise ValueError(f"Incorrect mode {self.mode!r}")

        t_start = time.monotonic()
        paths = ", ".join([os.path.relpath(p) for p in self.search_paths])
        logging.debug(f"Searching for test files in {paths}")

        finder = Finder()
        for root, _paths in self.search_paths.items():
            finder.add(root, *_paths, tolerant=True)
        finder.prepare()
        tree = finder.populate()
        n = sum([len(_fs) for _, _fs in tree.items()])
        logging.debug(f"Found {n} test files")

        on_options = on_options or []
        if config.get("build:options"):
            for opt, val in config.get("build:options").items():
                if val:
                    on_options.append(opt)
        on_options = dedup(on_options)

        logging.debug("Freezing test files")
        logging.debug(
            "Freezing test files with the following options:\n"
            f"  {self.avail_cpus=}\n"
            f"  {self.avail_cpus_per_test=}\n"
            f"  {self.avail_devices_per_test=}\n"
            f"  {on_options=}\n"
            f"  {keyword_expr=}\n"
            f"  {parameter_expr=}\n"
        )
        self.cases = Finder.freeze(
            tree,
            avail_cpus_per_test=self.avail_cpus_per_test,
            avail_devices_per_test=self.avail_devices_per_test,
            on_options=on_options,
            keyword_expr=keyword_expr,
            timelimit=test_timelimit,
            timeout_multiplier=timeout_multiplier,
            parameter_expr=parameter_expr,
        )
        cases_to_run = self.active_cases
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        duration = time.monotonic() - t_start
        self.db = Database(self.dotdir, self.cases)
        logging.debug(f"Done populating work tree ({duration:.2f}s.)")

    def setup_direct_queue(self) -> None:
        self.queue = DirectResourceQueue(
            self.avail_cpus, self.avail_devices, self.avail_workers, global_session_lock
        )
        self.queue.put(*self.active_cases)

    def setup_batch_queue(
        self,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
        scheduler: Optional[str] = None,
        scheduler_options: Optional[list[str]] = None,
        workers_per_batch: Optional[int] = None,
    ) -> None:
        batched: bool = batch_count is not None or batch_time is not None
        if not batched:
            raise ValueError("Expected batched == True")

        batch_stores = glob.glob(os.path.join(self.dotdir, "stage/batch/*"))

        cases_to_run = self.active_cases
        partitions: list[set[TestCase]]
        if batch_count:
            partitions = partition_n(cases_to_run, n=batch_count)
        else:
            assert batch_time is not None
            partitions = partition_t(cases_to_run, t=batch_time)
        n = len(partitions)
        N = len(batch_stores) + 1
        batches = [
            b_factory(p, i, n, N, scheduler=scheduler, avail_workers=workers_per_batch)
            for i, p in enumerate(partitions, start=1)
            if len(p)
        ]
        for batch in batches:
            batch.setup(*(scheduler_options or []))
        self.queue = BatchResourceQueue(
            self.avail_cpus, self.avail_devices, self.avail_workers, global_session_lock
        )
        self.queue.put(*batches)
        fd: dict[int, list[str]] = {}
        for batch in batches:
            cases = fd.setdefault(batch.world_rank, [])
            cases.extend([case.id for case in batch])

        file = os.path.join(self.dotdir, "stage/batch", str(N), "index")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            json.dump({"index": fd}, fh, indent=2)
        return

    def apply_batch_filter(self, batch_store: Optional[int], batch_no: Optional[int]) -> None:
        dir = os.path.join(self.dotdir, "stage/batch")
        if batch_store is None:
            batch_store = len(os.listdir(dir))  # use latest
        file = os.path.join(self.dotdir, "stage/batch", str(batch_store), "index")
        with open(file, "r") as fh:
            fd = json.load(fh)
        case_ids: list[str] = fd["index"][str(batch_no)]
        # mask tests and then later enable based on additional conditions
        for case in self.cases:
            if case.id in case_ids:
                case.status.set("ready")
            elif not case.masked:
                case.status.set("masked", f"case is not in batch {batch_no}")
        return None

    def batch_log(self, batch_no: int, batch_store: Optional[int]) -> str:
        dir = os.path.join(self.dotdir, "stage/batch")
        if batch_store is None:
            batch_store = len(os.listdir(dir))  # use latest
        index = os.path.join(dir, str(batch_store), "index")
        with open(index) as fh:
            fd = json.load(fh)
            n = len(fd["index"])
        f = os.path.join(dir, str(batch_store), f"out.{n}.{batch_no}.txt")
        return f

    def filter(
        self,
        batch_no: Optional[int] = None,
        batch_store: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        start: Optional[str] = None,
        avail_cpus_per_test: Optional[int] = None,
        avail_devices_per_test: Optional[int] = None,
        case_specs: Optional[list[str]] = None,
    ) -> None:
        if self.state != 1:
            raise ValueError(f"Expected state == 1 (got {self.state})")
        if batch_no is not None:
            self.apply_batch_filter(batch_store, batch_no)
            return
        explicit_start_path = start is not None
        if start is None:
            start = self.work_tree
        elif not os.path.isabs(start):
            start = os.path.join(self.work_tree, start)
        start = os.path.normpath(start)
        # mask tests and then later enable based on additional conditions
        for case in self.cases:
            if case.masked:
                continue
            if not case.exec_dir.startswith(start):
                case.status.set("masked", "Unreachable from start directory")
                continue
            if case_specs is not None:
                if any(case.matches(_) for _ in case_specs):
                    case.status.set("ready")
                else:
                    case.status.set("masked", colorize("deselected by @*b{testspec expression}"))
                continue
            elif explicit_start_path:
                case.status.set("ready")
                continue
            if case.status != "ready":
                s = f"deselected due to previous status: {case.status.cname}"
                case.status.set("masked", s)
                if avail_cpus_per_test and case.processors > avail_cpus_per_test:
                    continue
                if avail_devices_per_test and case.devices > avail_devices_per_test:
                    continue
                when_expr: list[str] = []
                if parameter_expr:
                    when_expr.append(f"parameters={parameter_expr!r}")
                if keyword_expr:
                    when_expr.append(f"keywords={keyword_expr!r}")
                if when_expr:
                    match = directives.when(
                        " ".join(when_expr),
                        parameters=case.parameters,
                        keywords=case.keywords(implicit=True),
                    )
                    if match:
                        case.status.set("ready")
        if not self.active_cases:
            raise EmptySession()

    def setup_queue(
        self,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
        scheduler: Optional[str] = None,
        scheduler_options: Optional[list[str]] = None,
        workers_per_batch: Optional[int] = None,
    ):
        if scheduler is None:
            if batch_count is not None or batch_time is not None:
                raise ValueError("batched execution requires a scheduler")
            self.setup_direct_queue()
        else:
            if batch_count is None and batch_time is None:
                batch_time = default_batchsize
            self.setup_batch_queue(
                batch_count=batch_count,
                batch_time=batch_time,
                scheduler=scheduler,
                scheduler_options=scheduler_options,
                workers_per_batch=workers_per_batch,
            )
        self.state = 2

    def run(
        self,
        *args: str,
        timeout: Optional[float] = None,
        fail_fast: bool = False,
        verbose: bool = False,
    ) -> int:
        if self.state != 2:
            raise ValueError(
                f"Expected state == 2 (got {self.state}), did you forget to call setup_queue?"
            )
        if config.get("config:debug"):
            verbose = True
        self.start = time.monotonic()
        if not self.queue:
            raise ValueError("This session's queue was not set up")
        if self.queue.empty():
            raise ValueError("There are no cases to run in this session")
        with self.rc_environ():
            with working_dir(self.work_tree):
                self.process_testcases(
                    *args, timeout=timeout or default_timeout, fail_fast=fail_fast, verbose=verbose
                )
        self.finish = time.monotonic()
        return self.returncode

    def teardown(self) -> None:
        finished: list[TestCase]
        if isinstance(self.queue, DirectResourceQueue):
            finished = self.queue.finished()
        else:
            finished = [case for batch in self.queue.finished() for case in batch]
        with self.rc_environ():
            for case in finished:
                with working_dir(case.exec_dir):
                    for hook in plugin.plugins("test", "teardown"):
                        logging.debug(f"Calling the {hook.specname} plugin")
                        hook(case)
                with working_dir(self.work_tree):
                    case.teardown()
        for hook in plugin.plugins("session", "teardown"):
            hook(self)

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        save_env: dict[str, Optional[str]] = {}
        variables = dict(config.get("variables"))
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        level = logging.get_level()
        os.environ["NVTEST_LOG_LEVEL"] = logging.get_level_name(level)
        yield
        for var, save_val in save_env.items():
            if save_val is not None:
                os.environ[var] = save_val
            else:
                os.environ.pop(var)

    def setup_testcases(
        self,
        cases: list[TestCase],
        copy_all_resources: bool = False,
        timeout_multipler: float = 1.0,
    ) -> None:
        logging.debug("Setting up test case directories")
        ts: TopologicalSorter = TopologicalSorter()
        for case in cases:
            ts.add(case, *case.dependencies)
        with self.rc_environ():
            with working_dir(self.work_tree):
                ts.prepare()
                while ts.is_active():
                    group = ts.get_ready()
                    args = zip(
                        group,
                        repeat(self.work_tree),
                        repeat(copy_all_resources),
                        repeat(timeout_multipler),
                    )
                    parallel.starmap(_setup_individual_case, list(args))
                    for case in group:
                        # Since setup is run in a multiprocessing pool, the internal
                        # state is lost and needs to be updated
                        case.refresh()
                        assert case.status.value in ("skipped", "ready", "pending")
                        with working_dir(case.exec_dir):
                            for hook in plugin.plugins("test", "setup"):
                                hook(case)
                    ts.done(*group)

    def process_testcases(
        self, *args: str, timeout: Union[int, float], fail_fast: bool, verbose: bool = False
    ) -> None:
        futures: dict = {}
        auto_cleanup: bool = True
        duration = lambda: time.monotonic() - self.start

        try:
            with ProcessPoolExecutor(max_workers=self.avail_workers) as ppe:
                while True:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        self.print_status()
                    if not verbose:
                        self.print_progress_bar()
                    if timeout >= 0.0 and duration() > timeout:
                        raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                    try:
                        iid_obj = self.queue.get()
                        if iid_obj is None:
                            time.sleep(0.01)
                            continue
                        iid, obj = iid_obj
                    except EmptyQueue:
                        break
                    future = ppe.submit(obj, *args, verbose=verbose)
                    callback = partial(self.update_from_future, iid, fail_fast)
                    future.add_done_callback(callback)
                    futures[iid] = (obj, future)
        except BaseException as e:
            if ppe._processes:
                for proc in ppe._processes:
                    os.kill(proc, signal.SIGINT)
            ppe.shutdown(wait=True)
            if isinstance(e, KeyboardInterrupt):
                self.returncode = signal.SIGINT.value
                auto_cleanup = False
            elif isinstance(e, FailFast):
                name, code = e.args
                self.returncode = code
                auto_cleanup = False
                raise StopExecution(f"fail_fast: {name}", code)
            else:
                logging.error(traceback.format_exc())
                self.returncode = compute_returncode(self.queue.cases())
                raise
        else:
            if not verbose:
                self.print_progress_bar(last=True)
            self.returncode = compute_returncode(self.queue.cases())
        finally:
            if auto_cleanup:
                for case in self.queue.cases():
                    if case.status == "ready":
                        case.status.set("failed", "Case failed to start")
                        case.save()
                    elif case.status == "running":
                        case.status.set("failed", "Case failed to stop")
                        case.save()

    def update_from_future(
        self,
        obj_no: int,
        fail_fast: bool,
        future: Future,
    ) -> None:
        if future.cancelled():
            return
        try:
            future.result()
        except BrokenProcessPool:
            # The future was probably killed by fail_fast or a keyboard interrupt
            return

        obj: Union[TestCase, Batch] = self.queue.done(obj_no)
        if not isinstance(obj, (Batch, TestCase)):
            logging.error(f"Expected TestCase or Batch, got {obj.__class__.__name__}")
            return

        # The case (or batch) was run in a subprocess.  The object must be
        # refreshed so that the state in this main thread is up to date.
        obj.refresh()
        if isinstance(obj, TestCase):
            self.db.update([obj])
            if fail_fast and obj.status != "success":
                code = compute_returncode([obj])
                raise FailFast(str(obj), code)
        else:
            assert isinstance(obj, Batch)
            fd = self.db.read()
            for case in obj:
                if case.id not in fd:
                    logging.error(f"case ID {case.id} not in batch {obj.world_rank}")
                    continue
                if case.status.value != fd[case.id]["status"].value:
                    fs = case.status.value
                    ss = fd[case.id]["status"].value
                    logging.warning(
                        f"batch {obj.world_rank}, {case}: "
                        f"expected status of future.result to be {ss}, not {fs}"
                    )
            if fail_fast and any(_.status != "success" for _ in obj):
                code = compute_returncode(obj.cases)
                raise FailFast(str(obj), code)

    def print_progress_bar(self, last: bool = False) -> None:
        with global_session_lock:
            progress(self.active_cases, time.monotonic() - self.start)
            if last:
                logging.emit("\n")

    def print_status(self):
        def count(objs) -> int:
            return sum([1 if isinstance(obj, TestCase) else len(obj) for obj in objs])

        with global_session_lock:
            p = d = f = t = 0
            done = count(self.queue.finished())
            busy = count(self.queue.busy())
            notrun = count(self.queue.queued())
            total = done + busy + notrun
            for obj in self.queue.finished():
                if isinstance(obj, TestCase):
                    obj = [obj]
                for case in obj:
                    if case.status == "success":
                        p += 1
                    elif case.status == "diffed":
                        d += 1
                    elif case.status == "timeout":
                        t += 1
                    else:
                        f += 1
            fmt = "%d/%d running, %d/%d done, %d/%d queued "
            fmt += "(@g{%d pass}, @y{%d diff}, @r{%d fail}, @m{%d timeout})"
            text = colorize(fmt % (busy, total, done, total, notrun, total, p, d, f, t))
            n = clen(text)
            header = colorize("@*c{%s}" % " status ".center(n + 10, "="))
            footer = colorize("@*c{%s}" % "=" * (n + 10))
            pad = colorize("@*c{====}")
            logging.lmit(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")

    def print_overview(self) -> None:
        def unreachable(c):
            return c.status == "skipped" and c.status.details.startswith("Unreachable")

        logging.info(f"Available cpus: {self.avail_cpus}")
        logging.info(f"Available cpus per test: {self.avail_cpus_per_test}")
        if self.avail_devices:
            logging.info(f"Available devices: {self.avail_devices}")
            logging.info(f"Available devices per test: {self.avail_devices_per_test}")
        logging.info(f"Maximum number of asynchronous jobs: {self.avail_workers}")
        cases = self.cases
        files = {case.file for case in cases}
        _, cases = partition(cases, lambda c: unreachable(c))
        t = "@*{collected %d tests from %d files}" % (len(cases), len(files))
        logging.info(colorize(t))
        cases_to_run = [case for case in cases if not case.masked and not case.skipped]
        files = {case.file for case in cases_to_run}
        t = "@*g{running} %d test cases from %d files" % (len(cases_to_run), len(files))
        logging.info(colorize(t))
        skipped = [case for case in cases if case.skipped or case.masked]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            reason = case.status.details
            assert isinstance(reason, str)
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        logging.info(colorize("@*b{skipping} %d test cases" % len(skipped)))
        reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
        for reason in reversed(reasons):
            logging.emit(f"• {skipped_reasons[reason]} {reason.lstrip()}\n")
        return

    @staticmethod
    def cformat(case: TestCase, show_log: bool = False) -> str:
        id = colorize("@*b{%s}" % case.id[:7])
        if case.masked:
            string = "@*c{EXCLUDED} %s %s: %s" % (id, case.pretty_repr(), case.status.details)
            return colorize(string)
        string = "%s %s %s" % (case.status.cname, id, case.pretty_repr())
        if case.duration > 0:
            string += " (%.2fs.)" % case.duration
        elif case.status == "skipped":
            string += ": Skipped due to %s" % case.status.details
        if show_log:
            f = os.path.relpath(case.logfile(), os.getcwd())
            string += colorize(": @m{%s}" % f)
        return string

    def print_summary(self) -> None:
        cases = self.active_cases
        if not cases:
            logging.info("Nothing to report")
            return

        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.masked:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)

        nonpass = ("skipped", "diffed", "timeout", "failed")
        level = logging.get_level()
        if level < logging.INFO and len(totals):
            logging.info(colorize("@*{Short test summary info}"))
        elif any(r in totals for r in nonpass):
            logging.info(colorize("@*{Short test summary info}"))
        if level < logging.DEBUG and "masked" in totals:
            for case in sorted(totals["masked"], key=lambda t: t.name):
                logging.emit(self.cformat(case) + "\n")
        if level < logging.INFO:
            for status in ("ready", "success"):
                if status in totals:
                    for case in sorted(totals[status], key=lambda t: t.name):
                        logging.emit(self.cformat(case) + "\n")
        for status in nonpass:
            if status in totals:
                for case in sorted(totals[status], key=lambda t: t.name):
                    logging.emit(self.cformat(case) + "\n")

    def print_footer(self, duration: float = -1) -> None:
        cases = self.active_cases
        if duration == -1:
            finish = max(_.finish for _ in cases)
            start = min(_.start for _ in cases)
            duration = finish - start

        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.masked:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        N = len(self.active_cases)
        summary_parts = ["@*b{%d total}" % N]
        for member in Status.colors:
            n = len(totals.get(member, []))
            if n:
                c = Status.colors[member]
                stat = totals[member][0].status.name
                summary_parts.append(colorize("@%s{%d %s}" % (c, n, stat.lower())))
        ts = hhmmss(duration)
        logging.info(colorize("@*{Session done} -- %s in @*{%s}" % (", ".join(summary_parts), ts)))

    def print_durations(self, N: int) -> None:
        cases = [case for case in self.active_cases if case.duration > 0]
        sorted_cases = sorted(cases, key=lambda x: x.duration)
        if N > 0:
            sorted_cases = sorted_cases[-N:]
        logging.info(f"Slowest {len(sorted_cases)} durations")
        for case in sorted_cases:
            logging.emit("  %6.2f     %s\n" % (case.duration, case.pretty_repr()))


def _setup_individual_case(case, exec_root, copy_all_resources, timeout_multiplier):
    case.setup(
        exec_root, copy_all_resources=copy_all_resources, timeout_multiplier=timeout_multiplier
    )


class EmptySession(Exception):
    def __init__(self):
        super().__init__("No test cases to run")


class DirectoryExistsError(Exception):
    pass
