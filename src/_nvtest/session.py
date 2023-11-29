import glob
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
from . import paths
from . import plugin
from .error import StopExecution
from .finder import Finder
from .mark.match import deselect_by_keyword
from .mark.match import deselect_by_parameter
from .queue import Queue
from .queue import factory as q_factory
from .runner import factory as r_factory
from .test import AbstractTestFile
from .test.enums import Result
from .test.enums import Skip
from .test.partition import Partition
from .test.partition import partition_n
from .test.partition import partition_t
from .test.testcase import TestCase
from .util import tty
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.lock import Lock
from .util.lock import WriteTransaction
from .util.misc import digits
from .util.returncode import compute_returncode
from .util.time import timeout as timeout_context

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
        if calling_func not in (Session.create, Session.load, Session.copy):
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
        max_workers: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        batch_config: Optional[BatchConfig] = None,
        copy_all_resources: bool = False,
        ignore_vvt: bool = False,
    ) -> "Session":
        if config.has_scope("session"):
            raise ValueError("cannot create new session when another session is active")
        self = cls()
        self.mode = "w"
        self.id = 0

        self.exitstatus = -1
        self.max_cores_per_test = max_cores_per_test or config.get("machine:cpu_count")
        self.max_workers = max_workers or 5
        self.search_paths = search_paths
        self.batch_config = batch_config or Session.BatchConfig()

        self._create_config(
            work_tree,
            search_paths=self.search_paths,
            max_cores_per_test=self.max_cores_per_test,
            max_workers=self.max_workers,
            keyword_expr=keyword_expr,
            on_options=on_options,
            parameter_expr=parameter_expr,
            batch_config=self.batch_config.asdict(),
            copy_all_resources=copy_all_resources,
            ignore_vvt=ignore_vvt,
        )
        tty.debug(f"Creating new nvtest session in {config.get('session:start')}")

        t_start: float = time.time()
        for hook in plugin.plugins("session", "setup"):
            hook(self)

        tree = self.populate(search_paths, ignore_vvt=ignore_vvt)

        tty.debug(
            "Freezing test files with the following options: ",
            f"{max_cores_per_test=}",
            f"{on_options=}",
            f"{keyword_expr=}",
            f"{parameter_expr=}",
        )

        self.cases = Finder.freeze(
            tree,
            cpu_count=self.max_cores_per_test,
            on_options=on_options,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
        )

        for hook in plugin.plugins("test", "discovery"):
            for case in self.cases:
                hook(self, case)

        cases_to_run = self.cases_to_run()
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)

        mkdirp(self.index_dir)
        mkdirp(self.stage)

        lock_path = os.path.join(self.dotdir, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session")

        self.setup_testcases(cases_to_run, copy_all_resources=copy_all_resources)

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
            work_items, workers=self.max_workers, cpu_count=self.max_cores_per_test
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
    def load(cls, *, session_no: Optional[int] = None, mode: str = "r") -> "Session":
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
        if session_no is not None:
            n_sessions = len(os.listdir(os.path.join(self.dotdir, "stage")))
            assert session_no < n_sessions
            self.id = session_no
        elif mode == "r":
            self.id = len(os.listdir(os.path.join(self.dotdir, "stage"))) - 1
        else:
            self.id = -1
        return self

    @classmethod
    def load_batch(
        cls,
        *,
        batch_no: int,
        session_no: Optional[int] = None,
    ) -> "Session":
        self = Session.load(session_no=session_no, mode="a")
        n = max(3, digits(len(os.listdir(self.batchdir))))
        f = os.path.join(self.batchdir, f"{batch_no:0{n}d}")
        case_ids: list[str] = [_.strip() for _ in open(f).readlines() if _.split()]
        for case in self.cases:
            if case.id in case_ids:
                case.skip = Skip()
                case.result = Result("notrun")
            elif not case.skip:
                case.skip = Skip("case is not in batch")
        cases = self.cases_to_run()
        self.queue = q_factory(
            cases, workers=self.max_workers, cpu_count=self.max_cores_per_test
        )
        return self

    @classmethod
    def copy(cls, *, mode: str = "a") -> "Session":
        self = Session.load(mode=mode)
        self.id = len(os.listdir(os.path.join(self.dotdir, "stage")))
        return self

    def _create_config(self, work_tree: str, **kwds: Any) -> None:
        work_tree = os.path.abspath(work_tree)
        config.set("session:work_tree", work_tree, scope="session")
        config.set("session:invocation_dir", os.getcwd(), scope="session")
        start = os.path.relpath(work_tree, os.getcwd()) or "."
        config.set("session:start", start, scope="session")
        for key, value in kwds.items():
            config.set(f"session:{key}", value, scope="session")
        for attr in ("sockets_per_node", "cores_per_socket", "cpu_count"):
            value = config.get(f"machine:{attr}", scope="local")
            if value is not None:
                config.set(f"machine:{attr}", value, scope="session")
        for section in ("config", "variables"):
            data = config.get(section, scope="local") or {}
            for key, value in data.items():
                config.set(f"{section}:{key}", value, scope="session")
        dotdir = os.path.join(work_tree, config.config_dir)
        mkdirp(dotdir)
        with open(os.path.join(dotdir, "config"), "w") as fh:
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
        return os.path.join(self.dotdir, "stage", f"{self.id:03d}")

    @property
    def batchdir(self):
        path = os.path.join(self.stage, "batch")
        return path

    @property
    def results_file(self):
        p = os.path.join(self.stage, "tests")
        return p

    def populate(
        self, treeish: dict[str, list[str]], ignore_vvt: bool = False
    ) -> dict[str, set[AbstractTestFile]]:
        assert self.mode == "w"
        tty.debug("Populating test session")
        finder = Finder()
        for root, _paths in treeish.items():
            tty.debug(f"Adding tests in {root}")
            finder.add(root, *_paths)
        finder.prepare()
        tree = finder.populate(ignore_vvt=ignore_vvt)
        return tree

    def filter(
        self,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        start: Optional[str] = None,
        max_cores_per_test: Optional[int] = None,
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
            if case.result != Result.NOTRUN and not case.exec_dir.startswith(start):
                case.skip = Skip(Skip.UNREACHABLE)
                continue
            if case_specs is not None and any(case.matches(_) for _ in case_specs):
                case.skip = Skip()
                case.result = Result("notrun")
                continue
            if case.result not in (Result.NOTDONE, Result.NOTRUN, Result.SETUP):
                skip_reason = f"previous test result: {case.result.cname}"
                case.skip = Skip(skip_reason)
                if not case.exec_dir.startswith(start):
                    continue
                if max_cores_per_test and case.size > max_cores_per_test:
                    continue
                if parameter_expr:
                    param_skip = deselect_by_parameter(case.parameters, parameter_expr)
                    if not param_skip:
                        case.skip = Skip()
                        case.result = Result("notrun")
                        continue
                if keyword_expr:
                    kwds = set(case.keywords(implicit=True))
                    kw_skip = deselect_by_keyword(kwds, keyword_expr)
                    if not kw_skip:
                        case.skip = Skip()
                        case.result = Result("notrun")
        cases = self.cases_to_run()
        if not cases:
            tty.die("No test cases to run")
        self.save_active_case_data(
            cases,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
            start=start,
        )
        self.queue = q_factory(
            cases, workers=self.max_workers, cpu_count=max_cores_per_test
        )

    def run(
        self,
        runner: Optional[str] = None,
        timeout: int = 60 * 60,
        runner_options: Optional[list[str]] = None,
        fail_fast: bool = False,
        analyze_only: bool = False,
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
        try:
            with self.rc_environ():
                with working_dir(self.work_tree):
                    self.process_testcases(
                        timeout=timeout, fail_fast=fail_fast, analyze_only=analyze_only
                    )
        finally:
            self.returncode = compute_returncode(self.queue.cases)
        return self.returncode

    def teardown(self):
        with self.rc_environ():
            for case in self.cases_to_run():
                with working_dir(case.exec_dir):
                    for hook in plugin.plugins("test", "teardown"):
                        tty.debug(f"Calling the {hook.specname} plugin")
                        hook(self, case)
                with working_dir(self.work_tree):
                    case.teardown()
        for hook in plugin.plugins("session", "teardown"):
            hook(self)

    def cases_to_run(self) -> list[TestCase]:
        return [
            case
            for case in self.cases
            if not case.skip
            and case.result in (Result.NOTRUN, Result.NOTDONE, Result.SETUP)
        ]

    def set_pythonpath(self, environ) -> None:
        pythonpath = [paths.prefix]
        if "PYTHONPATH" in environ:
            pythonpath.extend(environ["PYTHONPATH"].split(os.pathsep))
        if "PYTHONPATH" in os.environ:
            pythonpath.extend(os.environ["PYTHONPATH"].split(os.pathsep))
        environ["PYTHONPATH"] = os.pathsep.join(pythonpath)
        return

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        save_env: dict[str, Optional[str]] = {}
        variables = dict(config.get("variables"))
        self.set_pythonpath(variables)
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        os.environ["NVTEST_SESSION_NO"] = str(self.id)
        os.environ["NVTEST_LOG_LEVEL"] = str(tty.get_log_level())
        yield
        for var, save_val in save_env.items():
            if save_val is not None:
                os.environ[var] = save_val
            else:
                os.environ.pop(var)

    def setup_testcases(
        self, cases: list[TestCase], copy_all_resources: bool = False
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
                    cpu_count = config.get("machine:cpu_count")
                    pool = multiprocessing.Pool(processes=cpu_count)
                    result = pool.starmap(_setup_individual_case, args)
                    pool.close()
                    pool.join()
                    attrs = dict(result)
                    for case in group:
                        # Since setup is run in a multiprocessing pool, the internal
                        # state is lost and needs to be updated
                        case.update(attrs[case.fullname])
                        if not case.skip:
                            case.result = Result("setup")
                        case.dump()
                        with working_dir(case.exec_dir):
                            for hook in plugin.plugins("test", "setup"):
                                hook(self, case)
                    ts.done(*group)

    def process_testcases(
        self, *, timeout: int, fail_fast: bool, analyze_only: bool
    ) -> None:
        self._futures = {}
        timeout_message = f"Test suite execution exceeded time out of {timeout} s."
        try:
            with timeout_context(timeout, timeout_message=timeout_message):
                with ProcessPoolExecutor(max_workers=self.max_workers) as self.ppe:
                    while True:
                        try:
                            i, entity = self.queue.pop_next()
                        except StopIteration:
                            return
                        future = self.ppe.submit(self.runner, entity, analyze_only)
                        callback = partial(
                            self.update_from_future, i, entity, fail_fast
                        )
                        future.add_done_callback(callback)
                        self._futures[i] = (entity, future)
        finally:
            for entity, future in self._futures.values():
                if future.running():
                    entity.kill()
            for case in self.queue.cases:
                if case.result == Result.SETUP:
                    case.result = Result("notdone")
                    case.dump()

    def update_from_future(
        self,
        ent_no: int,
        entity: Union[Partition, TestCase],
        fail_fast: bool,
        future: Future,
    ) -> None:
        attrs = future.result()
        obj: Union[TestCase, Partition] = self.queue.mark_as_complete(ent_no)
        assert id(obj) == id(entity)
        if isinstance(obj, Partition):
            fd = load_test_results(self.stage)
            for case in obj:
                assert case.id in fd
                assert case.fullname in attrs
                assert attrs[case.fullname]["result"] == fd[case.id]["result"]
                case.update(fd[case.id])
            for case in obj:
                if fail_fast and case.result != Result.PASS:
                    self.ppe.shutdown(wait=False, cancel_futures=True)
                    code = compute_returncode([case])
                    raise StopExecution(f"fail_fast: {case} did not pass", code)
        else:
            assert isinstance(obj, TestCase)
            obj.update(attrs[obj.fullname])
            fd = obj.asdict("start", "finish", "result")
            with WriteTransaction(self.lock):
                with open(self.results_file, "a") as fh:
                    fh.write(json.dumps({obj.id: fd}) + "\n")
            if fail_fast and attrs[obj.fullname].result != Result.PASS:
                self.ppe.shutdown(wait=False, cancel_futures=True)
                code = compute_returncode([obj])
                raise StopExecution(f"fail_fast: {obj} did not pass", code)

    def _load_testcases(self) -> list[TestCase]:
        with open(os.path.join(self.index_dir, "cases")) as fh:
            fd = json.load(fh)
        pat = os.path.join(self.dotdir, "stage/*/tests")
        for file in sorted(glob.glob(pat)):
            with open(file) as fh:
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
        save_attrs = ["start", "finish", "result"]

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
