import glob
import inspect
import json
import os
import signal
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
from .runner import factory as r_factory
from .test.partition import Partition
from .test.partition import partition_n
from .test.partition import partition_t
from .test.status import Status
from .test.testcase import TestCase
from .third_party.lock import Lock
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction
from .util import keyboard
from .util import logging
from .util import parallel
from .util.color import clen
from .util.color import colorize
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.misc import dedup
from .util.misc import partition
from .util.returncode import compute_returncode

default_batchsize = 30 * 60  # 30 minutes
REUSE_SCHEDULER = "==REUSE_SCHEDUER=="


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
            "status": [case.status.value, case.status.details],
            "returncode": case.returncode,
            "dependencies": [dep.id for dep in case.dependencies],
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
            with open(file, "a") as fh:
                for case in cases:
                    cd = self._single_case_entry(case)
                    fh.write(json.dumps({case.id: cd}) + "\n")

    def load(self) -> list[TestCase]:
        """Load the test results

        Returns:
            The list of ``TestCase``s

        """
        fd: dict[str, dict]
        with ReadTransaction(self.lock):
            file = os.path.join(self.directory, "index/cases")
            with open(file, "r") as fh:
                fd = json.load(fh)
            file = os.path.join(self.directory, "stage/cases")
            with open(file, "r") as fh:
                for line in fh:
                    if line.split():
                        for case_id, value in json.loads(line).items():
                            fd[case_id].update(value)
        ts: TopologicalSorter = TopologicalSorter()
        for id, kwds in fd.items():
            ts.add(id, *kwds["dependencies"])
        cases: dict[str, TestCase] = {}
        for id in ts.static_order():
            kwds = fd[id]
            dependencies = kwds.pop("dependencies")
            if "exec_root" not in kwds:
                kwds["exec_root"] = os.path.dirname(self.directory)
            case = TestCase.from_dict(kwds)
            case.dependencies = [cases[dep] for dep in dependencies]
            cases[case.id] = case
        return list(cases.values())

    def read(self) -> dict[str, dict]:
        """Read the results file and return a dictionary of the stored ``TestCase`` attributions"""
        with ReadTransaction(self.lock):
            lines = open(os.path.join(self.directory, "stage/cases")).readlines()
        fd: dict[str, dict] = {}
        for line in lines:
            if line.split():
                for case_id, value in json.loads(line.strip()).items():
                    fd.setdefault(case_id, {}).update(value)
        return fd

    def makeindex(self, cases: list[TestCase]) -> None:
        """Store each ``TestCase`` in ``cases`` as a dictionary in the index file"""
        files: dict[str, set[str]] = {}
        indexed: dict[str, Any] = {}
        for case in cases:
            files.setdefault(case.file_root, set()).add(case.file_path)
            indexed[case.id] = case.asdict()
            indexed[case.id]["dependencies"] = [dep.id for dep in case.dependencies]
        file = os.path.join(self.directory, "index/files")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            json.dump({k: list(v) for (k, v) in files.items()}, fh, indent=2)
        file = os.path.join(self.directory, "index/cases")
        with open(file, "w") as fh:
            json.dump(indexed, fh, indent=2)
        file = os.path.join(self.directory, "stage/cases")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            for case in cases:
                if case.masked:
                    continue
                cd = self._single_case_entry(case)
                fh.write(json.dumps({case.id: cd}) + "\n")

    def reindex(self) -> None:
        """Filter the results file to contain only the latest test results"""
        cases = self.load()
        seen: set[str] = set()
        unique: list[TestCase] = []
        for case in reversed(cases):
            if case.id not in seen:
                unique.append(case)
                seen.add(case.id)
        file = os.path.join(self.directory, "stage/cases")
        with WriteTransaction(self.lock):
            with open(file, "w") as fh:
                for case in reversed(unique):
                    cd = self._single_case_entry(case)
                    fh.write(json.dumps({case.id: cd}) + "\n")


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
        copy_all_resources: bool = False,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
        scheduler: Optional[str] = None,
        scheduler_options: Optional[list[str]] = None,
    ) -> "Session":
        if config.has_scope("session"):
            raise ValueError("cannot create new session when another session is active")
        self = cls()
        self.mode = "w"
        self.exitstatus = -1
        logging.debug(f"Creating new test session in {work_tree}")
        t_start = time.time()

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
            copy_all_resources=copy_all_resources,
        )

        for hook in plugin.plugins("session", "setup"):
            hook(self)

        self.ini_options = dict(
            keyword_expr=keyword_expr,
            on_options=on_options,
            parameter_expr=parameter_expr,
            batch_count=batch_count,
            batch_time=batch_time,
            scheduler=scheduler,
            scheduler_options=scheduler_options,
            copy_all_resources=copy_all_resources,
        )
        file = os.path.join(self.dotdir, "params")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            variables = dict(vars(self))
            for attr in ("cases", "queue", "db", "runner"):
                variables.pop(attr, None)
            json.dump(variables, fh, indent=2)

        self.setup_runner(
            batch_count=batch_count,
            batch_time=batch_time,
            scheduler=scheduler,
            scheduler_options=scheduler_options,
        )

        duration = time.time() - t_start
        logging.debug(f"Done creating test session ({duration:.2f}s.)")

        self.state = 2
        return self

    @classmethod
    def load(cls, *, mode: str = "r") -> "Session":
        if mode not in "ra":
            raise ValueError(f"Incorrect mode {mode!r}")
        self = cls()
        self.work_tree = config.get("session:work_tree")
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

        t_start = time.time()
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
        duration = time.time() - t_start
        logging.debug(f"Done initializing session ({duration:.2f}s.)")

    def populate(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        copy_all_resources: bool = False,
    ) -> None:
        if self.mode != "w":
            raise ValueError(f"Incorrect mode {self.mode!r}")

        t_start = time.time()
        logging.debug("Populating work tree")

        finder = Finder()
        for root, _paths in self.search_paths.items():
            finder.add(root, *_paths, tolerant=True)
        finder.prepare()
        tree = finder.populate()

        on_options = on_options or []
        if config.get("build:options"):
            for opt, val in config.get("build:options").items():
                if val:
                    on_options.append(opt)
        on_options = dedup(on_options)

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
            parameter_expr=parameter_expr,
        )

        cases_to_run = self.active_cases
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)

        self.db = Database(self.dotdir, self.cases)
        self.setup_testcases(cases_to_run, copy_all_resources=copy_all_resources)
        duration = time.time() - t_start
        logging.debug(f"Done populating work tree ({duration:.2f}s.)")

    def setup_direct_queue(self) -> None:
        self.queue = DirectResourceQueue(self.avail_cpus, self.avail_devices, self.avail_workers)
        self.queue.put(*self.active_cases)

    def setup_batch_queue(
        self,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
    ) -> None:
        batched: bool = batch_count is not None or batch_time is not None
        if not batched:
            raise ValueError("Expected batched == True")

        batch_stores = glob.glob(os.path.join(self.dotdir, "stage/batch/*"))
        batch_store = len(batch_stores) + 1

        cases_to_run = self.active_cases
        batches: list[Partition]
        if batch_count:
            batches = partition_n(cases_to_run, n=batch_count, world_id=batch_store)
        else:
            assert batch_time is not None
            batches = partition_t(cases_to_run, t=batch_time, world_id=batch_store)
        self.queue = BatchResourceQueue(self.avail_cpus, self.avail_devices, self.avail_workers)
        self.queue.put(*batches)
        fd: dict[int, list[str]] = {}
        for batch in batches:
            cases = fd.setdefault(batch.world_rank, [])
            cases.extend([case.id for case in batch])

        file = os.path.join(self.dotdir, "stage/batch", str(batch_store), "index")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            json.dump({"index": fd}, fh, indent=2)
        return

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
                case.status.set("staged")
                case.unmask()
            elif not case.masked:
                case.mask = f"case is not in batch {batch_no}"
        return None

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
                case.mask = "Unreachable from start directory"
                continue
            if case_specs is not None:
                if any(case.matches(_) for _ in case_specs):
                    case.status.set("staged")
                else:
                    case.mask = colorize("deselected by @*b{testspec expression}")
                continue
            elif explicit_start_path:
                case.status.set("staged")
                continue
            if case.status != "staged":
                s = f"deselected due to previous status: {case.status.cname}"
                case.mask = s
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
                        case.status.set("staged")
                        case.unmask()
        if not self.active_cases:
            raise EmptySession()

    def setup_runner(
        self,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
        scheduler: Optional[str] = None,
        scheduler_options: Optional[list[str]] = None,
    ):
        if scheduler is not None:
            if batch_count is None and batch_time is None:
                batch_time = default_batchsize
        if batch_count is not None or batch_time is not None:
            if scheduler is None:
                raise ValueError("batched execution requires a scheduler")
        if scheduler is not None:
            reuse = scheduler == REUSE_SCHEDULER
            if reuse:
                scheduler = self.ini_options["scheduler"]
                scheduler_options = scheduler_options or self.ini_options["scheduler_options"]
            self.setup_batch_queue(batch_count=batch_count, batch_time=batch_time)
            self.runner = r_factory(scheduler, self, options=scheduler_options)
        else:
            self.setup_direct_queue()
            self.runner = r_factory("direct", self)
        queued = self.queue.queued()
        self.runner.validate(queued)
        for work_item in queued:
            self.runner.setup(work_item)
        self.state = 2

    def run(
        self,
        timeout: int = 60 * 60,
        fail_fast: bool = False,
    ) -> int:
        if self.state != 2:
            raise ValueError(
                f"Expected state == 2 (got {self.state}), did you forget to call setup_runner?"
            )
        if not self.queue:
            raise ValueError("This session's queue was not set up")
        if self.queue.empty():
            raise ValueError("There are no cases to run in this session")
        if not self.runner:
            raise ValueError("This session's runner was not set up")
        with self.rc_environ():
            with working_dir(self.work_tree):
                self.process_testcases(timeout=timeout, fail_fast=fail_fast)
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
    ) -> None:
        ts: TopologicalSorter = TopologicalSorter()
        for case in cases:
            ts.add(case, *case.dependencies)
        with self.rc_environ():
            with working_dir(self.work_tree):
                ts.prepare()
                while ts.is_active():
                    group = ts.get_ready()
                    args = zip(group, repeat(self.work_tree), repeat(copy_all_resources))
                    result = parallel.starmap(_setup_individual_case, list(args))
                    attrs = dict(result)
                    for case in group:
                        # Since setup is run in a multiprocessing pool, the internal
                        # state is lost and needs to be updated
                        case.update(attrs[case.id])
                        assert case.status.value in ("skipped", "staged")
                        case.dump()
                        with working_dir(case.exec_dir):
                            for hook in plugin.plugins("test", "setup"):
                                hook(case)
                    ts.done(*group)

    def process_testcases(self, *, timeout: int, fail_fast: bool) -> None:
        futures: dict = {}
        auto_cleanup: bool = True
        start = time.monotonic()
        duration = lambda: time.monotonic() - start

        try:
            with ProcessPoolExecutor(max_workers=self.avail_workers) as ppe:
                while True:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        self.print_status()
                    if duration() > timeout:
                        raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                    try:
                        iid_obj = self.queue.get()
                        if iid_obj is None:
                            time.sleep(0.001)
                            continue
                        iid, obj = iid_obj
                    except EmptyQueue:
                        break
                    future = ppe.submit(self.runner, obj)
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
            elif isinstance(e, FailFast):
                name, code = e.args
                self.returncode = code
                raise StopExecution(f"fail_fast: {name}", code)
            else:
                logging.error(traceback.format_exc())
                self.returncode = compute_returncode(self.queue.cases())
                raise
        else:
            self.returncode = compute_returncode(self.queue.cases())
        finally:
            for case in self.queue.cases():
                if case.status == "staged":
                    case.status.set("failed", "Case failed to start")
                    case.dump()

    def update_from_future(
        self,
        obj_no: int,
        fail_fast: bool,
        future: Future,
    ) -> None:
        if future.cancelled():
            return
        try:
            attrs = future.result()
        except BrokenProcessPool:
            # The future was probably killed by fail_fast or a keyboard interrupt
            return
        obj: Union[TestCase, Partition] = self.queue.done(obj_no)
        if isinstance(obj, Partition):
            fd = self.db.read()
            for case in obj:
                if case.id not in fd:
                    logging.error(f"case ID {case.id} not in batch {obj.world_rank}")
                    continue
                if case.fullname not in attrs:
                    logging.error(f"{case.fullname} not in batch {obj.world_rank}'s attrs")
                    continue
                if attrs[case.fullname]["status"] != fd[case.id]["status"]:
                    fs = attrs[case.fullname]["status"]
                    ss = fd[case.id]["status"]
                    logging.error(
                        f"batch {obj.world_rank}, {case}: "
                        f"expected status of future.result to be {ss[0]}, not {fs[0]}"
                    )
                    continue
                case.update(fd[case.id])
            if fail_fast and any(_.status != "success" for _ in obj):
                code = compute_returncode(obj)
                raise FailFast(str(obj), code)
        else:
            if not isinstance(obj, TestCase):
                logging.error(f"Expected TestCase, got {obj.__class__.__name__}")
                return
            obj.update(attrs[obj.fullname])
            self.db.update([obj])
            if fail_fast and obj.status != "success":
                code = compute_returncode([obj])
                raise FailFast(str(obj), code)

    def print_status(self):
        def count(objs) -> int:
            return sum([1 if isinstance(obj, TestCase) else len(obj) for obj in objs])

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
        logging.log(logging.ALWAYS, f"\n{header}\n{pad} {text} {pad}\n{footer}\n")

    def print_overview(self, duration: Optional[float] = None) -> None:
        def unreachable(c):
            return c.status == "skipped" and c.status.details.startswith("Unreachable")

        cases = self.cases
        files = {case.file for case in cases}
        _, cases = partition(cases, lambda c: unreachable(c))
        t = "@*{collected %d tests from %d files}" % (len(cases), len(files))
        if duration is not None:
            t += "@*{ in %.2fs.}" % duration
        logging.emit(colorize(t))
        cases_to_run = [case for case in cases if not case.masked and not case.skipped]
        files = {case.file for case in cases_to_run}
        t = "@*g{running} %d test cases from %d files" % (len(cases_to_run), len(files))
        logging.emit(colorize(t))
        skipped = [case for case in cases if case.skipped or case.masked]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            reason = case.mask if case.masked else case.status.details
            assert isinstance(reason, str)
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        logging.emit(colorize("@*b{skipping} %d test cases" % len(skipped)))
        reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
        for reason in reversed(reasons):
            logging.emit(f"  • {skipped_reasons[reason]} {reason.lstrip()}")
        return

    @staticmethod
    def cformat(case: TestCase, show_log: bool = False) -> str:
        id = colorize("@*b{%s}" % case.id[:7])
        if case.masked:
            string = "@*c{EXCLUDED} %s %s: %s" % (id, case.pretty_repr(), case.mask)
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

    def print_summary(
        self,
        duration: float = -1,
        durations: Optional[int] = None,
    ) -> None:
        cases = self.queue.cases()
        if not cases:
            logging.info("Nothing to report")
            return

        if duration == -1:
            finish = max(_.finish for _ in cases)
            start = min(_.start for _ in cases)
            duration = finish - start

        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.masked:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.iid, []).append(case)

        nonpass = ("skipped", "diffed", "timeout", "failed")
        level = logging.get_level()
        if level < logging.INFO and len(totals):
            logging.log(logging.ALWAYS, "Short test summary info", format="center")
        elif any(r in totals for r in nonpass):
            logging.log(logging.ALWAYS, "Short test summary info", format="center")
        if level < logging.DEBUG and "masked" in totals:
            for case in sorted(totals["masked"], key=lambda t: t.name):
                logging.emit(self.cformat(case))
        if level < logging.INFO:
            for status in ("staged", "success"):
                if status in totals:
                    for case in sorted(totals[status], key=lambda t: t.name):
                        logging.emit(self.cformat(case))
        for status in nonpass:
            if status in totals:
                for case in sorted(totals[status], key=lambda t: t.name):
                    logging.emit(self.cformat(case))

        if durations is not None:
            self._print_durations(cases, int(durations))

        summary_parts = []
        for member in Status.colors:
            n = len(totals.get(member, []))
            if n:
                c = Status.colors[member]
                stat = totals[member][0].status.name
                summary_parts.append(colorize("@%s{%d %s}" % (c, n, stat.lower())))
        text = ", ".join(summary_parts)
        logging.log(logging.ALWAYS, text + f" in {duration:.2f}s.", format="center")

    @staticmethod
    def _print_durations(cases: list[TestCase], N: int) -> None:
        cases = [case for case in cases if case.duration > 0]
        sorted_cases = sorted(cases, key=lambda x: x.duration)
        if N > 0:
            sorted_cases = sorted_cases[-N:]
        logging.log(logging.ALWAYS, f"Slowest {len(sorted_cases)} durations", format="center")
        for case in sorted_cases:
            logging.emit("  %6.2f     %s" % (case.duration, case.pretty_repr()))


def _setup_individual_case(case, exec_root, copy_all_resources):
    case.setup(exec_root, copy_all_resources=copy_all_resources)
    return (case.id, vars(case))


class EmptySession(Exception):
    def __init__(self):
        super().__init__("No test cases to run")


class DirectoryExistsError(Exception):
    pass
