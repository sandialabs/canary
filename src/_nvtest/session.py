"""
Phases of a test session
------------------------

A test session consists of the following phases:

Discovery:
  Search for test scripts in a test suite.

Setup:
  Order test scripts, create unique execution directories for each test, and
  copy/link necessary resources into the execution directory.

Run:
  For each test, move to its execution directory and run the test script, first
  ensuring that dependencies have been satisfied.

Cleanup:
  Remove artifacts created by the test.

Test session execution
----------------------

When ``nvtest run PATH`` is executed, ``PATH`` is searched for test files and
the session begun.  Once collected, tests are run in a separate execution
directory (default: ``./TestResults``).  Each test is run in its own
subdirectory with the following naming scheme:

.. code-block:: console

    TestResults/$path/$name.p1=v1.p2=v2...pn=vn

where ``$path`` is the directory name (including parents), relative to the
search path, of the test file, and ``$name`` is the basename of the test. The
``px=vx`` are the names of values of the test parameters (if any).

Consider, for example, the search path

.. code-block:: console

   $ tree tests
   tests/
   └── regression
       └── 2D
           ├── test_1.pyt
           └── test_2.pyt

and the corresponding test results directory tree:

.. code-block:: console

   $ tree TestResults
   TestResults/
   └── regression
       └── 2D
           ├── test_1
           │   ├── nvtest-out.txt
           │   └── test_1.pyt -> ../../../../tests/regressions/2D/test_1.pyt
           └── test_2
               ├── nvtest-out.txt
               └── test_2.pyt -> ../../../../tests/regressions/2D/test_2.pyt

The test's script is symbolically linked into the execution directory, where it
is ultimately executed.  The file ``nvtest-out.txt`` is the output from running
the test.
"""

import inspect
import json
import os
import signal
import sys
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
from .queue import Queue
from .queue import factory as q_factory
from .runner import factory as r_factory
from .test.partition import Partition
from .test.partition import partition_n
from .test.partition import partition_t
from .test.testcase import TestCase
from .third_party import rprobe
from .third_party.lock import Lock
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction
from .util import parallel
from .util import tty
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.misc import dedup
from .util.returncode import compute_returncode
from .util.time import timeout as timeout_context
from .util.tty.color import colorize

default_batchsize = 30 * 60  # 30 minutes


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
        with ReadTransaction(self.lock):
            lines = open(os.path.join(self.directory, "stage/cases")).readlines()
        fd: dict[str, dict] = {}
        for line in lines:
            if line.split():
                for case_id, value in json.loads(line.strip()).items():
                    fd.setdefault(case_id, {}).update(value)
        return fd

    def makeindex(self, cases: list[TestCase]) -> None:
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
    """Manages the test session"""

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
    queue: Queue
    lock: Lock
    db: Database

    def __init__(self) -> None:
        stack = inspect.stack()
        frame = stack[1][0]
        calling_func = None
        if "cls" in frame.f_locals:
            calling_func = getattr(frame.f_locals["cls"], frame.f_code.co_name, None)
        if calling_func not in (Session.create, Session.load):
            raise ValueError("Session must be created through one of its factory methods")
        self.state: int = 0
        self._avail_cpus = config.get("machine:cpu_count")
        self._avail_cpus_per_test = self.avail_cpus
        self._avail_workers = self.avail_cpus
        self._avail_devices = config.get("machine:device_count")
        self._avail_devices_per_test = self.avail_devices

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
        if arg > config.get("machine:cpu_count"):
            n = config.get("machine:cpu_count")
            raise ValueError(f"avail_cpus={arg} cannot exceed cpu_count={n}")
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
        tty.debug(f"Creating new test session in {work_tree}")
        t_start = time.time()

        if batch_count is not None or batch_time is not None:
            if scheduler is None:
                raise ValueError("batched execution requires a scheduler")

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

        if batch_count is not None or batch_time is not None:
            self.setup_batch_queue(batch_count=batch_count, batch_time=batch_time)
            self.runner = r_factory(scheduler, self, options=scheduler_options)
        else:
            self.setup_direct_queue()
            self.runner = r_factory("direct", self)
        self.runner.validate(self.queue.work_items)
        for work_item in self.queue.work_items:
            self.runner.setup(work_item)

        with open(os.path.join(self.dotdir, "params"), "w") as fh:
            variables = dict(vars(self))
            for attr in ("cases", "queue", "db", "runner"):
                variables.pop(attr, None)
            json.dump(variables, fh, indent=2)
        file = os.path.join(self.dotdir, "options")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            kwds = dict(
                keyword_expr=keyword_expr,
                on_options=on_options,
                parameter_expr=parameter_expr,
            )
            json.dump(kwds, fh, indent=2)

        duration = time.time() - t_start
        tty.debug(f"Done creating test session ({duration:.2f}s.)")

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
        tty.debug("Initializing session")
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
        tty.debug(f"Done initializing session ({duration:.2f}s.)")

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
        tty.debug("Populating work tree")

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

        tty.debug(
            "Freezing test files with the following options: ",
            f"{self.avail_cpus=}",
            f"{self.avail_cpus_per_test=}",
            f"{self.avail_devices_per_test=}",
            f"{on_options=}",
            f"{keyword_expr=}",
            f"{parameter_expr=}",
        )
        self.cases = Finder.freeze(
            tree,
            avail_cpus_per_test=self.avail_cpus_per_test,
            avail_devices_per_test=self.avail_devices_per_test,
            on_options=on_options,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
        )

        cases_to_run = [case for case in self.cases if not case.masked]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)

        self.db = Database(self.dotdir, self.cases)
        self.setup_testcases(cases_to_run, copy_all_resources=copy_all_resources)
        duration = time.time() - t_start
        tty.debug(f"Done populating work tree ({duration:.2f}s.)")

    def setup_direct_queue(self) -> None:
        self.queue = q_factory(
            [case for case in self.cases if not case.masked],
            avail_workers=self.avail_workers,
            avail_cpus=self.avail_cpus,
            avail_devices=self.avail_devices,
        )

    def setup_batch_queue(
        self,
        batch_count: Optional[int] = None,
        batch_time: Optional[float] = None,
    ) -> None:
        batched: bool = batch_count is not None or batch_time is not None
        if not batched:
            raise ValueError("Expected batched == True")

        cases_to_run = [case for case in self.cases if not case.masked]
        batches: list[Partition]
        if batch_count:
            batches = partition_n(cases_to_run, n=batch_count)
        else:
            batches = partition_t(cases_to_run, t=batch_time)
        self.queue = q_factory(
            batches,
            avail_workers=self.avail_workers,
            avail_cpus=self.avail_cpus,
            avail_devices=self.avail_devices,
        )
        fd: dict[int, list[str]] = {}
        for batch in batches:
            cases = fd.setdefault(batch.rank[0], [])
            cases.extend([case.id for case in batch])
        file = os.path.join(self.dotdir, "index/batches")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            json.dump({"batches": fd}, fh, indent=2)

    def filter(
        self,
        batch_no: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        start: Optional[str] = None,
        avail_cpus_per_test: Optional[int] = None,
        avail_devices_per_test: Optional[int] = None,
        case_specs: Optional[list[str]] = None,
    ) -> None:
        if self.state != 1:
            raise ValueError(f"Expected state == 1 (got {self.state})")
        if start is None:
            start = self.work_tree
        elif not os.path.isabs(start):
            start = os.path.join(self.work_tree, start)
        start = os.path.normpath(start)
        case_ids: list[str] = []
        if batch_no is not None:
            file = os.path.join(self.dotdir, "index/batches")
            with open(file, "r") as fh:
                fd = json.load(fh)
            case_ids.extend(fd["batches"][str(batch_no)])
        # mask tests and then later enable based on additional conditions
        for case in self.cases:
            if batch_no is not None:
                if case.id in case_ids:
                    case.status.set("staged")
                    case.unmask()
                else:
                    case.mask = f"case is not in batch {batch_no}"
                continue
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
        cases = [case for case in self.cases if not case.masked]
        if not cases:
            raise EmptySession()
        self.setup_direct_queue()
        self.runner = r_factory("direct", self)
        self.runner.validate(self.queue.work_items)
        self.state = 2

    def run(
        self,
        timeout: int = 60 * 60,
        fail_fast: bool = False,
    ) -> int:
        if self.state != 2:
            raise ValueError(f"Expected state == 2 (got {self.state})")
        if not self.queue:
            raise ValueError("This session's queue was not set up")
        if not self.queue.cases:
            raise ValueError("There are no cases to run in this session")
        if not self.runner:
            raise ValueError("This session's runner was not set up")
        with self.rc_environ():
            with working_dir(self.work_tree):
                self.process_testcases(timeout=timeout, fail_fast=fail_fast)
        return self.returncode

    def teardown(self):
        with self.rc_environ():
            for case in self.queue.completed_testcases():
                with working_dir(case.exec_dir):
                    for hook in plugin.plugins("test", "teardown"):
                        tty.debug(f"Calling the {hook.specname} plugin")
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
        os.environ["NVTEST_LOG_LEVEL"] = str(tty.get_log_level())
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
        processes: int = rprobe.cpu_count()
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
                        case.update(attrs[case.fullname])
                        assert case.status.value in ("skipped", "staged")
                        case.dump()
                        with working_dir(case.exec_dir):
                            for hook in plugin.plugins("test", "setup"):
                                hook(case)
                    ts.done(*group)

    def process_testcases(self, *, timeout: int, fail_fast: bool) -> None:
        futures: dict = {}
        timeout_message = f"Test suite execution exceeded time out of {timeout} s."
        auto_cleanup: bool = True
        try:
            with timeout_context(timeout, timeout_message=timeout_message):
                with ProcessPoolExecutor(max_workers=self.avail_workers) as ppe:
                    while True:
                        try:
                            i, entity = self.queue.pop_next(fail_fast=fail_fast)
                        except KeyboardInterrupt:
                            auto_cleanup = False
                            self.returncode = signal.SIGINT.value
                            for proc in ppe._processes:
                                if proc != os.getpid():
                                    os.kill(proc, 9)
                            raise
                        except FailFast as ex:
                            auto_cleanup = False
                            for proc in ppe._processes:
                                if proc != os.getpid():
                                    os.kill(proc, 9)
                            name, code = ex.args
                            self.returncode = code
                            raise StopExecution(f"fail_fast: {name}", code)
                        except StopIteration:
                            break
                        except BaseException:
                            traceback.print_exc(file=sys.stderr)
                            raise
                        future = ppe.submit(self.runner, entity)
                        callback = partial(self.update_from_future, i)
                        future.add_done_callback(callback)
                        futures[i] = (entity, future)
        finally:
            tty.reset()
            if auto_cleanup:
                for entity, future in futures.values():
                    if future.running():
                        entity.kill()
                for case in self.queue.cases:
                    if case.status == "staged":
                        tty.error(f"{case}: failed to start!")
                        case.status.set("failed", "Case failed to start")
                        case.dump()
                self.returncode = compute_returncode(self.queue.cases)

    def update_from_future(
        self,
        ent_no: int,
        future: Future,
    ) -> None:
        if future.cancelled():
            return
        entity = self.queue._running[ent_no]
        try:
            attrs = future.result()
        except BrokenProcessPool:
            # The future was probably killed by fail_fast or a keyboard interrupt
            return
        obj: Union[TestCase, Partition] = self.queue.mark_as_complete(ent_no)
        if id(obj) != id(entity):
            tty.error(f"{obj}: wrong future entity ID")
            return
        if isinstance(obj, Partition):
            fd = self.db.read()
            for case in obj:
                if case.id not in fd:
                    tty.error(f"case ID {case.id} not in batch {obj.rank[0]}")
                    continue
                if case.fullname not in attrs:
                    tty.error(f"{case.fullname} not in batch {obj.rank[0]}'s attrs")
                    continue
                if attrs[case.fullname]["status"] != fd[case.id]["status"]:
                    fs = attrs[case.fullname]["status"]
                    ss = fd[case.id]["status"]
                    tty.error(
                        f"batch {obj.rank[0]}, {case}: "
                        f"expected status of future.result to be {ss[0]}, not {fs[0]}"
                    )
                    continue
                case.update(fd[case.id])
        else:
            if not isinstance(obj, TestCase):
                tty.error(f"Expected TestCase, got {obj.__class__.__name__}")
                return
            obj.update(attrs[obj.fullname])
            self.db.update([obj])


def _setup_individual_case(case, exec_root, copy_all_resources):
    case.setup(exec_root, copy_all_resources=copy_all_resources)
    return (case.fullname, vars(case))


class EmptySession(Exception):
    def __init__(self):
        super().__init__("No test cases to run")


class DirectoryExistsError(Exception):
    pass
