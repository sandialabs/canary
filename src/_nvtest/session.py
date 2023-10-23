import glob
import inspect
import json
import multiprocessing
import os
import time
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from functools import partial
from itertools import repeat
from typing import Any
from typing import Generator
from typing import Optional
from typing import Union

from . import paths
from . import plugin
from .config import Config
from .error import StopExecution
from .finder import Finder
from .mark.match import deselect_by_keyword
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
from .util.misc import digits
from .util.returncode import compute_returncode
from .util.time import timeout

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
        def __init__(self, *, size_t: float = None, size_n: int = None) -> None:
            self.size_t = size_t
            self.size_n = size_n
            if self.size_t is not None and self.size_n is not None:
                raise TypeError("size_t and size_n are mutually exclusive")

        def __bool__(self) -> bool:
            return self.size_t is not None or self.size_n is not None

        def asdict(self):
            return vars(self)

    default_workdir = "./TestResults"
    mode: str
    id: int
    startdir: str
    rel_workdir: str
    exitstatus: int
    config: Config
    cpu_count: int
    max_workers: int
    search_paths: dict[str, list[str]]
    batch_config: BatchConfig
    cases: list[TestCase]
    queue: Queue

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
        workdir: str,
        search_paths: dict[str, list[str]],
        config: Optional[Config] = None,
        cpu_count: Optional[int] = None,
        max_workers: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        batch_config: BatchConfig = None,
        copy_all_resources: bool = False,
    ) -> "Session":
        self = cls()
        self.mode = "w"
        self.id = 0
        self.startdir = os.getcwd()
        self.rel_workdir = os.path.relpath(os.path.abspath(workdir), self.startdir)
        self.exitstatus = -1
        self.config = config or Config()
        self.cpu_count = cpu_count or self.config.machine.cpu_count
        self.max_workers = max_workers or 5
        self.search_paths = search_paths
        self.batch_config = batch_config or Session.BatchConfig()

        t_start = time.time()
        for hook in plugin.plugins("session", "setup"):
            hook(self)

        tree = self.populate(search_paths)
        with timed("freezing test tree"):
            self.cases = Finder.freeze(
                tree,
                cpu_count=self.cpu_count,
                on_options=on_options,
                keyword_expr=keyword_expr,
            )

        for hook in plugin.plugins("test", "discovery"):
            for case in self.cases:
                hook(self, case)
        cases_to_run = self.cases_to_run()
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)

        mkdirp(self.dotdir)
        mkdirp(self.index_dir)
        mkdirp(self.stage)

        with timed("Setting up test cases"):
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
            work_items, workers=self.max_workers, cpu_count=self.cpu_count
        )

        if batch_config:
            self.save_active_batch_data(work_items)  # type: ignore
        self.save_active_case_data(
            cases_to_run, keyword_expr=keyword_expr, on_options=on_options
        )

        with open(os.path.join(self.dotdir, "params"), "w") as fh:
            variables = dict(vars(self))
            for attr in ("config", "cases", "queue"):
                variables.pop(attr)
            variables["batch_config"] = self.batch_config.asdict()
            json.dump(variables, fh, indent=2)
        with open(self.config_file, "w") as fh:
            self.config.dump(fh)
        self.create_index(
            self.cases,
            cpu_count=self.cpu_count,
            keyword_expr=keyword_expr,
            on_options=on_options,
            copy_all_resources=copy_all_resources,
        )

        duration = time.time() - t_start
        tty.debug(f"Done setting up test session ({duration:.2f}s.)")
        tty.debug("Done creating new test session")
        return self

    @classmethod
    def load(
        cls, *, workdir: str, config: Optional[Config] = None, mode: str = "r"
    ) -> "Session":
        if not Session.is_workdir(workdir, ascend=True):
            raise ValueError(
                "not a nvtest session (or any of the parent directories): .nvtest"
            )
        assert mode in "ra"
        self = cls()
        workdir = self.find_workdir(workdir)
        self.mode = mode
        self.startdir = os.getcwd()
        self.rel_workdir = os.path.relpath(os.path.abspath(workdir), self.startdir)
        self.exitstatus = -1
        self.config = config or Config()
        self.config.load_user_config_file(self.config_file)
        assert os.path.exists(os.path.join(self.dotdir, "stage"))
        with open(os.path.join(self.dotdir, "params")) as fh:
            for (attr, value) in json.load(fh).items():
                if attr == "batch_config":
                    value = Session.BatchConfig(**value)
                setattr(self, attr, value)
        self.cases = self._load_testcases()
        self.id = -1
        if mode == "r":
            self.id = len(os.listdir(os.path.join(self.dotdir, "stage"))) - 1
        return self

    @classmethod
    def load_batch(
        cls, *, workdir: str, batch_no: int, config: Optional[Config] = None
    ) -> "Session":
        self = Session.load(workdir=workdir, config=config, mode="a")
        self.id = 0
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
            cases, workers=self.max_workers, cpu_count=self.cpu_count
        )
        return self

    @classmethod
    def copy(
        cls, *, workdir: str, config: Optional[Config] = None, mode: str = "a"
    ) -> "Session":
        self = Session.load(workdir=workdir, config=config, mode=mode)
        self.id = len(os.listdir(os.path.join(self.dotdir, "stage")))
        return self

    @property
    def log_level(self) -> int:
        return self.config.log_level

    @property
    def workdir(self) -> str:
        path = os.path.join(self.startdir, self.rel_workdir)
        return os.path.normpath(path)

    @property
    def dotdir(self) -> str:
        path = os.path.join(self.workdir, ".nvtest")
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
        self, treeish: dict[str, list[str]]
    ) -> dict[str, list[AbstractTestFile]]:
        assert self.mode == "w"
        with timed("populating test tree"):
            finder = Finder()
            for (root, _paths) in treeish.items():
                finder.add(root, *_paths)
            finder.prepare()
            tree = finder.populate()
        return tree

    def filter(
        self, keyword_expr: Optional[str] = None, start: Optional[str] = None
    ) -> None:
        if not self.cases:
            raise ValueError("This test session has not been setup")
        if start is not None:
            if not os.path.isabs(start):
                start = os.path.join(self.workdir, start)
            start = os.path.normpath(start)
        for case in self.cases:
            if case.result not in (Result.NOTDONE, Result.NOTRUN, Result.SETUP):
                skip_reason = f"previous test result: {case.result.cname}"
                case.skip = Skip(skip_reason)
                if start is not None and not case.exec_dir.startswith(start):
                    continue
                elif keyword_expr:
                    kwds = set(case.keywords(implicit=True))
                    kw_skip = deselect_by_keyword(kwds, keyword_expr)
                    if not kw_skip:
                        case.skip = Skip()
                        case.result = Result("notrun")
        cases = self.cases_to_run()
        self.save_active_case_data(cases, keyword_expr=keyword_expr, start=start)
        self.queue = q_factory(
            cases, workers=self.max_workers, cpu_count=self.cpu_count
        )

    def run(
        self,
        runner: str = None,
        timeout: int = 60 * 60,
        runner_options: list[str] = None,
        fail_fast: bool = False,
    ) -> int:
        with timed("running test cases"):
            if not self.queue:
                raise ValueError("This session's queue was not set up")
            if not self.queue.cases:
                raise ValueError("There are not cases to run in this session")
            self.runner = r_factory(
                runner or "direct",
                self,
                self.queue.cases,
                machine_config=self.config.machine,
                options=runner_options,
            )
            try:
                with self.rc_environ():
                    with working_dir(self.workdir):
                        self.process_testcases(timeout, fail_fast)
            finally:
                self.returncode = compute_returncode(self.queue.cases)
        return compute_returncode(self.queue.cases)

    def teardown(self):
        with timed("cleaning up test session"):
            with self.rc_environ():
                for case in self.cases_to_run():
                    with working_dir(case.exec_dir):
                        for hook in plugin.plugins("test", "teardown"):
                            tty.debug(f"Calling the {hook.specname} plugin")
                            hook(self, case)
                    with working_dir(self.workdir):
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

    @staticmethod
    def is_workdir(path: str, ascend: bool = False) -> bool:
        path = os.path.abspath(path)
        f1 = lambda d: os.path.join(d, ".nvtest/config")
        f2 = lambda d: os.path.join(d, ".nvtest/index")
        f3 = lambda d: os.path.join(d, ".nvtest/params")
        exists = os.path.exists
        while path != os.path.sep:
            if all((exists(f1(path)), exists(f2(path)), exists(f3(path)))):
                return True
            elif not ascend:
                break
            path = os.path.dirname(path)
        return False

    @staticmethod
    def find_workdir(start) -> str:
        path = os.path.abspath(start)
        f1 = lambda d: os.path.join(d, ".nvtest/config")
        f2 = lambda d: os.path.join(d, ".nvtest/index")
        f3 = lambda d: os.path.join(d, ".nvtest/params")
        exists = os.path.exists
        while True:
            if all((exists(f1(path)), exists(f2(path)), exists(f3(path)))):
                return path
            path = os.path.dirname(path)
            if path == "/":
                raise ValueError("Could not find workdir")

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
        variables = dict(self.config.variables)
        self.set_pythonpath(variables)
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        yield
        for var, save_val in save_env.items():
            if save_val is not None:
                os.environ[var] = save_val
            else:
                os.environ.pop(var)

    def setup_testcases(
        self, cases: list[TestCase], copy_all_resources: bool = False
    ) -> None:
        mkdirp(self.workdir)
        ts: TopologicalSorter = TopologicalSorter()
        for case in cases:
            ts.add(case, *case.dependencies)
        with self.rc_environ():
            with working_dir(self.workdir):
                ts.prepare()
                while ts.is_active():
                    group = ts.get_ready()
                    args = zip(group, repeat(self.workdir), repeat(copy_all_resources))
                    pool = multiprocessing.Pool(processes=self.config.machine.cpu_count)
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

    def process_testcases(self, _timeout: int, fail_fast: bool) -> None:
        self._futures = {}
        log_level = tty.get_log_level()
        timeout_message = f"Test suite execution exceeded time out of {_timeout} s."
        try:
            with timeout(_timeout, timeout_message=timeout_message):
                with ProcessPoolExecutor(max_workers=self.max_workers) as self.ppe:
                    while True:
                        try:
                            i, entity = self.queue.pop_next()
                        except StopIteration:
                            return
                        future = self.ppe.submit(self.runner, entity, log_level)
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
            with open(self.results_file, "a") as fh:
                obj.update(attrs[obj.fullname])
                fd = obj.asdict("start", "finish", "result")
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
                        for (case_id, value) in json.loads(line).items():
                            fd[case_id].update(value)
        ts: TopologicalSorter = TopologicalSorter()
        for (id, kwds) in fd.items():
            ts.add(id, *kwds["dependencies"])
        cases: dict[str, TestCase] = {}
        for id in ts.static_order():
            kwds = fd[id]
            dependencies = kwds.pop("dependencies")
            case = TestCase.from_dict(kwds)
            case.dependencies = [cases[dep] for dep in dependencies]
            cases[case.id] = case
        return list(cases.values())

    def create_index(self, cases: list[TestCase], **kwds: Any) -> None:
        files: dict[str, list[str]] = {}
        indexed: dict[str, Any] = {}
        for case in cases:
            files.setdefault(case.file_root, []).append(case.file_path)
            indexed[case.id] = case.asdict()
            indexed[case.id]["dependencies"] = [dep.id for dep in case.dependencies]
        with open(os.path.join(self.index_dir, "files"), "w") as fh:
            json.dump(files, fh, indent=2)
        with open(os.path.join(self.index_dir, "cases"), "w") as fh:
            json.dump(indexed, fh, indent=2)
        if kwds:
            with open(os.path.join(self.index_dir, "params"), "w") as fh:
                json.dump(kwds, fh, indent=2)

    def save_active_case_data(self, cases: list[TestCase], **kwds: Any):
        mkdirp(self.stage)
        save_attrs = ["start", "finish", "exec_root", "result"]
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
    with timed(f"setting up {case}"):
        case.setup(exec_root, copy_all_resources=copy_all_resources)
    return (case.fullname, vars(case))


def load_test_results(stage: str) -> dict[str, dict]:
    fd: dict[str, dict] = {}
    file = os.path.join(stage, "tests")
    with open(file) as fh:
        for line in fh:
            if line.split():
                for (case_id, value) in json.loads(line).items():
                    fd.setdefault(case_id, {}).update(value)
    return fd


@contextmanager
def timed(label: str):
    start = time.time()
    tty.debug(label.capitalize())
    yield
    duration = time.time() - start
    tty.debug(f"Done {label} ({duration:.2f}s.)")
