import glob
import json
import multiprocessing
import os
import re
import time
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from datetime import datetime
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

    default_workdir = "./TestResults"

    def __init__(self, *, workdir: str, mode: str = "r") -> None:
        assert mode in "raw"
        self.mode = mode
        self.tag = ""
        self.startdir = os.getcwd()
        self.stages: dict[str, dict[str, datetime]] = {}
        self._cases: Optional[list[TestCase]] = None
        self.exitstatus: int = -1
        self.tree: dict[str, list[AbstractTestFile]] = {}
        if mode == "w":
            self.init(workdir)
        else:
            self.load(workdir)

    def init(self, workdir: str) -> None:
        tty.verbose(f"Initializing test session in {workdir}")
        if workdir is None:
            workdir = self.default_workdir
        if os.path.exists(workdir):
            raise ValueError(f"workdir {workdir} already exists")
        self.config = Config()
        self.rel_workdir = os.path.relpath(os.path.abspath(workdir), self.startdir)
        self.inum = 0
        mkdirp(self.dotdir)
        mkdirp(self.index_dir)
        mkdirp(self.results_root)
        with open(self.config_file, "w") as fh:
            self.config.dump(fh)
        tty.verbose("Done initializing test session")

    def load(self, workdir: str) -> None:
        assert self.is_workdir(workdir)
        self.rel_workdir = os.path.relpath(os.path.abspath(workdir), self.startdir)
        self.config = Config(user_config_file=self.config_file)
        self.inum = len(os.listdir(self.results_root))
        self.cases = self._load_testcases()

    @property
    def workdir(self) -> str:
        path = os.path.join(self.startdir, self.rel_workdir)
        return os.path.normpath(path)

    @property
    def dotdir(self) -> str:
        path = os.path.join(self.workdir, ".nvtest")
        return path

    @property
    def results_root(self):
        path = os.path.join(self.dotdir, "results")
        return path

    @property
    def results_dir(self):
        path = os.path.join(self.results_root, f"{self.inum:03d}")
        return path

    @property
    def results_file(self):
        p = os.path.join(self.results_dir, "tests")
        return p

    @property
    def index_dir(self):
        path = os.path.join(self.dotdir, "index")
        return path

    @property
    def config_file(self):
        path = os.path.join(self.dotdir, "config")
        return path

    @property
    def duration(self):
        if "setup" not in self.stages:
            return -1
        start = self.stages["setup"]["start"]
        if "run" not in self.stages:
            finish = self.stages["setup"]["finish"]
        else:
            finish = self.stages["run"]["finish"]
        dt = finish - start
        return dt.seconds

    def dotpath(self, name: str) -> str:
        return os.path.join(self.dotdir, name + self.tag)

    def populate(self, treeish: dict[str, list[str]]) -> None:
        assert self.mode == "w"
        finder = Finder()
        for (root, _paths) in treeish.items():
            finder.add(root, *_paths)
        finder.prepare()
        self.tree = finder.populate()
        tree: dict[str, list[str]] = {}
        for files in self.tree.values():
            for file in files:
                tree.setdefault(file.root, []).append(file.path)
        with open(os.path.join(self.index_dir, "tree"), "w") as fh:
            json.dump(tree, fh, indent=2)

    @property
    def cases(self) -> list[TestCase]:
        return self._cases or []

    @cases.setter
    def cases(self, arg: list[TestCase]) -> None:
        self._cases = arg
        if self.mode == "w":
            for hook in plugin.plugins("test", "discovery"):
                for case in self._cases:
                    hook(self, case)

    def filter(
        self,
        cpu_count: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        start: Optional[str] = None,
    ) -> None:
        if start is not None:
            if not os.path.isabs(start):
                start = os.path.join(self.workdir, start)
            start = os.path.normpath(start)
        if not self.cases:
            self.cases = Finder.freeze(
                self.tree,
                cpu_count=cpu_count,
                on_options=on_options,
                keyword_expr=keyword_expr,
            )
            indexed: dict[str, Any] = {}
            for case in self.cases:
                indexed[case.id] = case.asdict()
                indexed[case.id]["dependencies"] = [dep.id for dep in case.dependencies]
            with open(os.path.join(self.index_dir, "cases"), "w") as fh:
                json.dump(indexed, fh, indent=2)
            with open(os.path.join(self.index_dir, "params"), "w") as fh:
                fd = {"keyword_expr": keyword_expr, "on_options": on_options}
                json.dump(fd, fh, indent=2)
        else:
            for case in self.cases:
                if case.result not in (Result.NOTDONE, Result.NOTRUN, Result.SETUP):
                    skip_reason = f"previous test result: {case.result.cname}"
                    case.skip = Skip(skip_reason)
                    if start is not None and not case.exec_dir.startswith(start):
                        continue
                    if keyword_expr:
                        kwds = set(case.keywords(implicit=True))
                        kw_skip = deselect_by_keyword(kwds, keyword_expr)
                        if not kw_skip:
                            case.skip = Skip()
                            case.result = Result("notrun")

    def setup(
        self,
        cpu_count: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        start: Optional[str] = None,
        max_workers: int = None,
        runner: str = None,
        runner_options: list[str] = None,
        batch_config: BatchConfig = None,
        copy_all_resources: bool = False,
    ) -> None:
        tty.verbose("Setting up test session")
        self.filter(
            cpu_count=cpu_count,
            keyword_expr=keyword_expr,
            on_options=on_options,
            start=start,
        )
        cases_to_run = self.cases_to_run()
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        for hook in plugin.plugins("session", "setup"):
            hook(self)
        stage = self.stages.setdefault("setup", {})
        stage["start"] = datetime.now()
        self.cpu_count = self.config.machine.cpu_count
        self.max_workers = self.cpu_count if max_workers is None else max_workers
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
        self.queue = q_factory(work_items, self.max_workers, self.cpu_count)
        self.runner = r_factory(
            runner or "direct",
            work_items,
            machine_config=self.config.machine,
            options=runner_options,
        )
        # Save empty results for cases to run
        mkdirp(self.results_dir)
        with open(self.results_file, "w") as fh:
            idata = {"start": -1, "finish": -1, "result": [Result.NOTRUN, ""]}
            for case in self.queue.cases:
                fh.write(json.dumps({case.id: idata}) + "\n")
        with open(os.path.join(self.results_dir, "params"), "w") as fh:
            fd = {"keyword_expr": keyword_expr, "on_options": on_options}
            json.dump(fd, fh, indent=2)

        # Now setup actual cases
        self.setup_testcases(copy_all_resources=copy_all_resources)
        stage["finish"] = datetime.now()
        duration = stage["finish"] - stage["start"]
        tty.verbose(f"Done setting up test session ({duration.seconds:.2f}s.)")

    def run(self, timeout: int = 3600, fail_fast: bool = False) -> int:
        tty.verbose("Running test cases")
        stage = self.stages.setdefault("run", {})
        stage["start"] = datetime.now()
        try:
            with self.rc_environ():
                with working_dir(self.workdir):
                    self.process_testcases(timeout, fail_fast)
        finally:
            stage["finish"] = datetime.now()
            self.returncode = compute_returncode(self.queue.cases)
        duration = stage["finish"] - stage["start"]
        tty.verbose(f"Done running test cases ({duration.seconds:.2f}s.)")
        return compute_returncode(self.queue.cases)

    def teardown(self):
        tty.verbose("Cleaning up session")
        stage = self.stages.setdefault("teardown", {})
        stage["start"] = datetime.now()
        with self.rc_environ():
            for case in self.queue.cases:
                with working_dir(case.exec_dir):
                    for hook in plugin.plugins("test", "teardown"):
                        tty.verbose(f"Calling the {hook.specname} plugin")
                        hook(self, case)
                with working_dir(self.workdir):
                    case.teardown()
        for hook in plugin.plugins("session", "teardown"):
            hook(self)
        stage["finish"] = datetime.now()
        duration = stage["finish"] - stage["start"]
        tty.verbose(f"Done cleaning up test session ({duration.seconds:.2f}s.)")

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
        f3 = lambda d: os.path.join(d, ".nvtest/results")
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
        f3 = lambda d: os.path.join(d, ".nvtest/results")
        exists = os.path.exists
        while True:
            if all((exists(f1(path)), exists(f2(path)), exists(f3(path)))):
                return path
            path = os.path.dirname(path)
            if path == "/":
                raise ValueError("Could not find workdir")

    @staticmethod
    def is_batch_file(file: Union[str, None]) -> bool:
        if file is None:
            return False
        pat = "^batch.json.[0-9]+.[0-9]+$"
        dir, name = os.path.split(file)
        return Session.is_workdir(dir, ascend=True) and bool(re.search(pat, name))

    @property
    def log_level(self) -> int:
        return self.config.log_level

    def dump(self):
        data: dict[str, Any] = {"config": self.config.asdict()}
        data["date"] = datetime.now().strftime("%c")
        f = os.path.join(self.dotdir, "session.json")
        with open(f, "w") as fh:
            json.dump({"session": data}, fh, indent=2)

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

    def setup_testcases(self, copy_all_resources: bool = False) -> None:
        tty.verbose("Setting up test cases")
        mkdirp(self.workdir)
        ts: TopologicalSorter = TopologicalSorter()
        for case in self.queue.cases:
            ts.add(case, *case.dependencies)
        with self.rc_environ():
            with working_dir(self.workdir):
                tty.verbose("Launching mulitprocssing pool to setup tests in parallel")
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

        tty.verbose("Done setting up test cases")

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
        with open(self.results_file, "a") as fh:
            for case in self.itercases(obj):
                case.update(attrs[case.fullname])
                if fail_fast and attrs[case.fullname].result != Result.PASS:
                    self.ppe.shutdown(wait=False, cancel_futures=True)
                    code = compute_returncode([case])
                    raise StopExecution(f"fail_fast: {case} did not pass", code)
                fd = {
                    "start": case.start,
                    "finish": case.finish,
                    "exec_root": case.exec_root,
                    "result": [case.result.name, case.result.reason],
                }
                fh.write(json.dumps({case.id: fd}) + "\n")

    def itercases(
        self, obj: Union[TestCase, Partition]
    ) -> Generator[TestCase, None, None]:
        if isinstance(obj, TestCase):
            yield obj
        else:
            for case in obj:
                yield case

    def _load_testcases(self) -> list[TestCase]:
        with open(os.path.join(self.index_dir, "cases")) as fh:
            fd = json.load(fh)
        pat = os.path.join(self.results_root, "*/tests")
        for file in sorted(glob.glob(pat)):
            with open(file) as fh:
                for line in fh:
                    if not line.split():
                        continue
                    for (key, value) in json.loads(line).items():
                        fd[key].update(value)
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


def _setup_individual_case(case, exec_root, copy_all_resources):
    tty.verbose(f"Setting up {case}")
    start = time.time()
    case.setup(exec_root, copy_all_resources=copy_all_resources)
    duration = time.time() - start
    tty.verbose(f"Done setting up {case} ({duration:.2f}s.)")
    return (case.fullname, vars(case))
