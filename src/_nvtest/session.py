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
import multiprocessing
import os
import time
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from functools import cached_property
from functools import partial
from itertools import repeat
from typing import Any
from typing import Generator
from typing import Optional
from typing import Union

from . import config
from . import directives
from . import plugin
from .error import StopExecution
from .finder import Finder
from .queue import Queue
from .queue import factory as q_factory
from .runner import factory as r_factory
from .test import AbstractTestFile
from .test.partition import Partition
from .test.partition import partition_n
from .test.partition import partition_t
from .test.testcase import TestCase
from .third_party.lock import Lock
from .third_party.lock import WriteTransaction
from .util import tty
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.misc import dedup
from .util.misc import digits
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


class Session:
    """Manages the test session

    :param InvocationParams invocation_params:
        Object containing parameters regarding the :func:`pytest.main`
        invocation.
    """

    class BatchConfig:
        def __init__(
            self, *, size_t: Optional[float] = None, size_n: Optional[int] = None
        ) -> None:
            self.size_t = size_t
            self.size_n = size_n
            if self.size_t is not None and self.size_n is not None:
                raise TypeError("size_t and size_n are mutually exclusive")

        def __bool__(self) -> bool:
            return self.size_t is not None or self.size_n is not None

        def asdict(self):
            return vars(self)

    default_work_tree = "./TestResults"
    mode: str
    id: int
    startdir: str
    exitstatus: int
    max_cores_per_test: int
    max_devices_per_test: int
    max_workers: int
    search_paths: dict[str, list[str]]
    batch_config: BatchConfig
    cases: list[TestCase]
    queue: Queue
    lock: Lock

    def __init__(self) -> None:
        stack = inspect.stack()
        frame = stack[1][0]
        calling_func = None
        if "cls" in frame.f_locals:
            calling_func = getattr(frame.f_locals["cls"], frame.f_code.co_name, None)
        if calling_func not in (Session.create, Session.load):
            raise ValueError(
                "Session must be created through one of its factory methods"
            )

    @classmethod
    def create(
        cls,
        *,
        work_tree: str,
        search_paths: dict[str, list[str]],
        max_cores_per_test: Optional[int] = None,
        max_devices_per_test: Optional[int] = None,
        max_workers: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        batch_config: Optional[BatchConfig] = None,
        copy_all_resources: bool = False,
    ) -> "Session":
        if config.has_scope("session"):
            raise ValueError("cannot create new session when another session is active")
        self = cls()
        self.mode = "w"

        self.exitstatus = -1
        self.max_cores_per_test = max_cores_per_test or config.get("machine:cpu_count")
        self.max_devices_per_test = max_devices_per_test or config.get(
            "machine:device_count"
        )
        if max_workers is None:
            max_workers = 5 if batch_config else self.max_cores_per_test
        self.max_workers = max_workers
        self.search_paths = search_paths
        self.batch_config = batch_config or Session.BatchConfig()

        on_options = on_options or []
        if config.get("build:options"):
            for opt, val in config.get("build:options").items():
                if val:
                    on_options.append(opt)
        on_options = dedup(on_options)

        self._create_config(
            work_tree,
            search_paths=self.search_paths,
            max_cores_per_test=self.max_cores_per_test,
            max_devices_per_test=self.max_devices_per_test,
            max_workers=self.max_workers,
            keyword_expr=keyword_expr,
            on_options=on_options,
            parameter_expr=parameter_expr,
            batch_config=self.batch_config.asdict(),
            copy_all_resources=copy_all_resources,
        )
        tty.debug(f"Creating new nvtest session in {config.get('session:start')}")

        t_start: float = time.time()
        for hook in plugin.plugins("session", "setup"):
            hook(self)

        tree = self.populate(search_paths)

        tty.debug(
            "Freezing test files with the following options: ",
            f"{max_cores_per_test=}",
            f"{max_devices_per_test=}",
            f"{on_options=}",
            f"{keyword_expr=}",
            f"{parameter_expr=}",
        )

        self.cases = Finder.freeze(
            tree,
            cpu_count=self.max_cores_per_test,
            device_count=self.max_devices_per_test,
            on_options=on_options,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
        )

        cases_to_run = [case for case in self.cases if not case.masked]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)

        mkdirp(self.index_dir)
        mkdirp(self.stage)

        lock_path = os.path.join(self.dotdir, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session")

        self.setup_testcases(
            cases_to_run, copy_all_resources=copy_all_resources, cpu_count=max_workers
        )

        # Setup the queue
        work_items: Union[list[TestCase], list[Partition]]
        if batch_config:
            if batch_config.size_t is not None:
                work_items = partition_t(cases_to_run, t=batch_config.size_t)
            elif batch_config.size_n is not None:
                work_items = partition_n(cases_to_run, n=batch_config.size_n)
            else:
                raise ValueError("cannot determine batch configuration")
        else:
            work_items = cases_to_run

        self.queue = q_factory(
            work_items,
            workers=self.max_workers,
            cpu_count=self.max_cores_per_test,
            device_count=self.max_devices_per_test,
        )

        if batch_config:
            self.save_active_batch_data(work_items)  # type: ignore

        self.save_active_case_data(
            cases_to_run,
            keyword_expr=keyword_expr,
            on_options=on_options,
            parameter_expr=parameter_expr,
        )

        with open(os.path.join(self.dotdir, "params"), "w") as fh:
            variables = dict(vars(self))
            for attr in ("cases", "queue", "lock"):
                variables.pop(attr)
            variables["batch_config"] = self.batch_config.asdict()
            json.dump(variables, fh, indent=2)
        self.create_index(self.cases)

        duration = time.time() - t_start
        tty.debug(f"Done creating test session ({duration:.2f}s.)")
        return self

    @classmethod
    def load(cls, *, mode: str = "r") -> "Session":
        work_tree = config.get("session:work_tree")
        if not work_tree:
            raise ValueError(
                "not a nvtest session (or any of the parent directories): .nvtest"
            )
        assert mode in "ra"
        self = cls()
        self.mode = mode
        self.exitstatus = -1
        lock_path = os.path.join(self.dotdir, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session")
        assert os.path.exists(os.path.join(self.dotdir, "stage"))
        with open(os.path.join(self.dotdir, "params")) as fh:
            for attr, value in json.load(fh).items():
                if attr == "batch_config":
                    value = Session.BatchConfig(**value)
                setattr(self, attr, value)
        self.cases = self._load_testcases()
        return self

    @classmethod
    def load_batch(cls, *, batch_no: int) -> "Session":
        self = Session.load(mode="a")
        n = max(3, digits(len(os.listdir(self.batchdir))))
        f = os.path.join(self.batchdir, f"{batch_no:0{n}d}")
        case_ids: list[str] = [_.strip() for _ in open(f).readlines() if _.split()]
        for case in self.cases:
            if case.id in case_ids:
                case.status.set("staged")
            elif not case.masked:
                case.mask = f"case is not in batch {batch_no}"
        cases = [case for case in self.cases if not case.masked]
        self.queue = q_factory(
            cases,
            workers=self.max_workers,
            cpu_count=self.max_cores_per_test,
            device_count=self.max_devices_per_test,
        )
        return self

    def _create_config(self, work_tree: str, **kwds: Any) -> None:
        work_tree = os.path.abspath(work_tree)
        config.set("session:work_tree", work_tree, scope="session")
        config.set("session:invocation_dir", config.invocation_dir, scope="session")
        start = os.path.relpath(work_tree, os.getcwd()) or "."
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
        file = os.path.join(work_tree, config.config_dir, "config")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            config.dump(fh, scope="session")

    @cached_property
    def work_tree(self) -> str:
        return config.get("session:work_tree", scope="session")

    @property
    def dotdir(self) -> str:
        path = os.path.join(self.work_tree, ".nvtest")
        return path

    @property
    def index_dir(self):
        path = os.path.join(self.dotdir, "index")
        return path

    @property
    def config_file(self):
        path = os.path.join(self.dotdir, "config")
        return path

    @property
    def stage(self) -> str:
        return os.path.join(self.dotdir, "stage")

    @property
    def batchdir(self):
        path = os.path.join(self.stage, "batch")
        return path

    @property
    def results_file(self):
        p = os.path.join(self.stage, "tests")
        return p

    def populate(
        self, treeish: dict[str, list[str]]
    ) -> dict[str, set[AbstractTestFile]]:
        assert self.mode == "w"
        tty.debug("Populating test session")
        finder = Finder()
        for root, _paths in treeish.items():
            tty.debug(f"Adding tests in {root}")
            finder.add(root, *_paths)
        finder.prepare()
        tree = finder.populate()
        return tree

    def filter(
        self,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        start: Optional[str] = None,
        max_cores_per_test: Optional[int] = None,
        max_devices_per_test: Optional[int] = None,
        case_specs: Optional[list[str]] = None,
    ) -> None:
        if not self.cases:
            raise ValueError("This test session has not been setup")
        if start is None:
            start = self.work_tree
        elif not os.path.isabs(start):
            start = os.path.join(self.work_tree, start)
        start = os.path.normpath(start)
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
            if case.status != "staged":
                s = f"deselected due to previous test status: {case.status.cname}"
                case.mask = s
                if max_cores_per_test and case.cpu_count > max_cores_per_test:
                    continue
                if max_devices_per_test and case.device_count > max_devices_per_test:
                    continue
                if parameter_expr:
                    match = directives.when(parameter_expr, parameters=case.parameters)
                    if match:
                        case.status.set("staged")
                        continue
                if keyword_expr:
                    kwds = set(case.keywords(implicit=True))
                    match = directives.when(keyword_expr, keywords=kwds)
                    if match:
                        case.status.set("staged")
        cases = [case for case in self.cases if case.status == "staged"]
        if not cases:
            raise EmptySession()
        self.queue = q_factory(
            cases,
            workers=self.max_workers,
            cpu_count=max_cores_per_test,
            device_count=max_devices_per_test,
        )

    def run(
        self,
        runner: Optional[str] = None,
        timeout: int = 60 * 60,
        runner_options: Optional[list[str]] = None,
        fail_fast: bool = False,
        execute_analysis_sections: bool = False,
    ) -> int:
        if not self.queue:
            raise ValueError("This session's queue was not set up")
        if not self.queue.cases:
            raise ValueError("There are no cases to run in this session")
        self.runner = r_factory(
            runner or "direct",
            self,
            self.queue.cases,
            options=runner_options,
        )
        with self.rc_environ():
            with working_dir(self.work_tree):
                self.process_testcases(
                    timeout=timeout,
                    fail_fast=fail_fast,
                    execute_analysis_sections=execute_analysis_sections,
                )
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
        cpu_count: int = 5,
    ) -> None:
        mkdirp(self.work_tree)
        ts: TopologicalSorter = TopologicalSorter()
        for case in cases:
            ts.add(case, *case.dependencies)
        with self.rc_environ():
            with working_dir(self.work_tree):
                ts.prepare()
                while ts.is_active():
                    group = ts.get_ready()
                    args = zip(
                        group, repeat(self.work_tree), repeat(copy_all_resources)
                    )
                    pool = multiprocessing.Pool(processes=cpu_count)
                    result = pool.starmap(_setup_individual_case, args)
                    pool.close()
                    pool.join()
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

    def process_testcases(
        self, *, timeout: int, fail_fast: bool, execute_analysis_sections: bool
    ) -> None:
        futures = {}
        timeout_message = f"Test suite execution exceeded time out of {timeout} s."
        try:
            with timeout_context(timeout, timeout_message=timeout_message):
                with ProcessPoolExecutor(max_workers=self.max_workers) as self.ppe:
                    while True:
                        try:
                            i, entity = self.queue.pop_next()
                        except StopIteration:
                            return
                        kwds = {"execute_analysis_sections": execute_analysis_sections}
                        future = self.ppe.submit(self.runner, entity, kwds)
                        callback = partial(self.update_from_future, i, fail_fast)
                        future.add_done_callback(callback)
                        futures[i] = (entity, future)
        finally:
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
        fail_fast: bool,
        future: Future,
    ) -> None:
        entity = self.queue._running[ent_no]
        attrs = future.result()
        obj: Union[TestCase, Partition] = self.queue.mark_as_complete(ent_no)
        if id(obj) != id(entity):
            raise RuntimeError("wrong future entity ID")
        if isinstance(obj, Partition):
            fd = load_test_results(self.stage)
            for case in obj:
                if case.id not in fd:
                    raise RuntimeError("case ID not in partition")
                if case.fullname not in attrs:
                    raise RuntimeError("case fullname not in partition attrs")
                if attrs[case.fullname]["status"] != fd[case.id]["status"]:
                    fs = attrs[case.fullname]["status"]
                    ss = fd[case.id]["status"]
                    raise RuntimeError(f"future.status ({fs}) != case.status {ss}")
                case.update(fd[case.id])
            for case in obj:
                if fail_fast and case.status != "success":
                    self.ppe.shutdown(wait=False, cancel_futures=True)
                    code = compute_returncode([case])
                    raise StopExecution(f"fail_fast: {case} did not pass", code)
        else:
            if not isinstance(obj, TestCase):
                raise RuntimeError(f"Expected TestCase, got {obj.__class__.__name__}")
            obj.update(attrs[obj.fullname])
            fd = obj.asdict("start", "finish", "status", "returncode")
            with WriteTransaction(self.lock):
                with open(self.results_file, "a") as fh:
                    fh.write(json.dumps({obj.id: fd}) + "\n")
            if fail_fast and attrs[obj.fullname].status != "success":
                self.ppe.shutdown(wait=False, cancel_futures=True)
                code = compute_returncode([obj])
                raise StopExecution(f"fail_fast: {obj} did not pass", code)

    def _load_testcases(self) -> list[TestCase]:
        with open(os.path.join(self.index_dir, "cases")) as fh:
            fd = json.load(fh)
        with open(self.results_file) as fh:
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
                kwds["exec_root"] = self.work_tree
            case = TestCase.from_dict(kwds)
            case.dependencies = [cases[dep] for dep in dependencies]
            cases[case.id] = case
        return list(cases.values())

    def create_index(self, cases: list[TestCase]) -> None:
        files: dict[str, set[str]] = {}
        indexed: dict[str, Any] = {}
        for case in cases:
            files.setdefault(case.file_root, set()).add(case.file_path)
            indexed[case.id] = case.asdict()
            indexed[case.id]["dependencies"] = [dep.id for dep in case.dependencies]
        with open(os.path.join(self.index_dir, "files"), "w") as fh:
            json.dump({k: list(v) for (k, v) in files.items()}, fh, indent=2)
        with open(os.path.join(self.index_dir, "cases"), "w") as fh:
            json.dump(indexed, fh, indent=2)

    def save_active_case_data(self, cases: list[TestCase], **kwds: Any):
        mkdirp(self.stage)
        save_attrs = ["start", "finish", "status"]

        with WriteTransaction(self.lock):
            with open(self.results_file, "w") as fh:
                for case in cases:
                    idata = case.asdict(*save_attrs)
                    if "dependencies" in idata:
                        idata["dependencies"] = [dep.id for dep in case.dependencies]
                    fh.write(json.dumps({case.id: idata}) + "\n")
        with open(os.path.join(self.stage, "params"), "w") as fh:
            json.dump(kwds, fh)

    def save_active_batch_data(self, batches: list[Partition]) -> None:
        mkdirp(self.batchdir)
        n = max(3, digits(len(batches)))
        for batch in batches:
            i, _ = batch.rank
            with open(os.path.join(self.batchdir, f"{i:0{n}d}"), "w") as fh:
                for case in batch:
                    fh.write(f"{case.id}\n")


def _setup_individual_case(case, exec_root, copy_all_resources):
    case.setup(exec_root, copy_all_resources=copy_all_resources)
    return (case.fullname, vars(case))


def load_test_results(stage: str) -> dict[str, dict]:
    lines = open(os.path.join(stage, "tests")).readlines()
    fd: dict[str, dict] = {}
    for line in lines:
        if line.split():
            for case_id, value in json.loads(line.strip()).items():
                fd.setdefault(case_id, {}).update(value)
    return fd


class EmptySession(Exception):
    def __init__(self):
        super().__init__("No test cases to run")
