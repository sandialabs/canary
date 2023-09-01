import json
import multiprocessing
import os
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from functools import partial
from itertools import repeat
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Union

from . import plugin
from .queue import factory as q_factory
from .runner import factory as r_factory
from .test.enums import Result
from .test.partition import Partition
from .test.partition import partition_t
from .test.testcase import TestCase
from .util import tty
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.returncode import compute_returncode
from .util.time import timeout

if TYPE_CHECKING:
    from .session import Session


class Executor:
    _tc_done_file = "testcases.json"
    _tc_prog_file = "testcases.jsons"

    def __init__(
        self,
        session: "Session",
        cases: list[TestCase],
        *,
        runner: str,
        max_workers: int = 5,
        batch_size: Optional[int] = None,
        runner_options: Optional[list[Any]] = None,
    ):
        self.session = session
        config = self.session.config
        self.cpu_count = config.machine.cpu_count
        self.max_workers = self.cpu_count if max_workers < 0 else max_workers
        tty.verbose(f"Tests will be run with {self.max_workers} concurrent workers")
        self.workdir = self.session.workdir
        tty.verbose(f"Execution directory: {self.workdir}")

        self.cases = cases
        self.work_items: Union[list[TestCase], list[Partition]] = cases
        if batch_size is not None:
            self.work_items = partition_t(cases, t=batch_size)
        tty.verbose(f"Initializing executor for {len(self.work_items)} test items")

        self.queue = q_factory(self.work_items, self.max_workers, self.cpu_count)
        self.runner = r_factory(
            runner,
            self.work_items,
            machine_config=self.session.config.machine,
            options=runner_options,
        )
        self.stages: dict[str, dict[str, datetime]] = {}

    @property
    def tc_done_file(self) -> str:
        return os.path.join(self.session.dotdir, self._tc_done_file)

    @property
    def tc_prog_file(self) -> str:
        return os.path.join(self.session.dotdir, self._tc_prog_file)

    def setup(self, copy_all_resources: bool = False):
        tty.verbose("Setting up test executor")
        stage = self.stages.setdefault("setup", {})
        stage["start"] = datetime.now()
        self.setup_testcases(copy_all_resources=copy_all_resources)
        stage["end"] = datetime.now()
        tty.verbose("Done setting up test executor")

    def run(self, timeout: int = 3600) -> None:
        tty.verbose("Running test cases")
        stage = self.stages.setdefault("run", {})
        stage["start"] = datetime.now()
        try:
            with self.session.rc_environ():
                with working_dir(self.workdir):
                    self.process_testcases(timeout)
            if not self.session.config.debug:
                force_remove(self.tc_prog_file)
        finally:
            self.returncode = compute_returncode(self.cases)
            with open(self.tc_done_file, "w") as fh:
                json.dump([c.asdict() for c in self.cases], fh, indent=2)
        stage["end"] = datetime.now()
        tty.verbose("Done running test cases")

    def teardown(self):
        tty.verbose("Cleaning up executor")
        with self.session.rc_environ():
            for case in self.cases:
                with working_dir(case.exec_dir):
                    for name, func in plugin.plugins("test", "teardown"):
                        tty.verbose(f"Calling the {name} plugin")
                        func(
                            self.session,
                            case,
                            on_options=self.session.option.on_options,
                        )
                with working_dir(self.workdir):
                    case.teardown()
        tty.verbose("Done tearing down up executor")
        return

    def setup_testcases(self, copy_all_resources: bool = False) -> None:
        tty.verbose("Setting up test cases")
        mkdirp(self.workdir)
        ts: TopologicalSorter = TopologicalSorter()
        for case in self.cases:
            ts.add(case, *case.dependencies)
        force_remove(self.tc_prog_file)
        with self.session.rc_environ():
            with working_dir(self.workdir):
                tty.verbose("Launching mulitprocssing pool to setup tests in parallel")
                ts.prepare()
                while ts.is_active():
                    group = ts.get_ready()
                    args = zip(group, repeat(self.workdir), repeat(copy_all_resources))
                    pool = multiprocessing.Pool(processes=self.cpu_count)
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
                            kwds = dict(on_options=self.session.option.on_options)
                            for _, func in plugin.plugins("test", "setup"):
                                func(self.session, case, **kwds)
                    ts.done(*group)
        tty.verbose("Done setting up test cases")

    def process_testcases(self, _timeout: int) -> None:
        self._futures = {}
        log_level = self.session.config.log_level
        timeout_message = f"Test suite execution exceeded time out of {_timeout} s."
        try:
            with timeout(_timeout, timeout_message=timeout_message):
                with ProcessPoolExecutor(max_workers=self.max_workers) as ppe:
                    while True:
                        try:
                            i, entity = self.queue.pop_next()
                        except StopIteration:
                            return
                        future = ppe.submit(self.runner, entity, log_level)
                        callback = partial(self.update_from_future, i, entity)
                        future.add_done_callback(callback)
                        self._futures[i] = (entity, future)
        finally:
            for entity, future in self._futures.values():
                if future.running():
                    entity.kill()
            for case in self.cases:
                if case.result == Result.SETUP:
                    case.result = Result("notdone")
                    case.dump()

    def update_from_future(
        self, ent_no: int, entity: Union[Partition, TestCase], future: Future
    ) -> None:
        attrs = future.result()
        obj: Union[TestCase, Partition] = self.queue.mark_as_complete(ent_no)
        assert id(obj) == id(entity)
        with open(self.tc_prog_file, "a") as fh:
            if isinstance(obj, Partition):
                for case in obj:
                    case.update(attrs)
                    fh.write(case.to_json() + "\n")
            else:
                obj.update(attrs)
                fh.write(obj.to_json() + "\n")


class SingleBatchDirectExecutor(Executor):
    def __init__(
        self,
        session: "Session",
        batch: Partition,  # type: ignore
        *,
        max_workers: int = 5,
    ):
        super().__init__(session, batch, max_workers=max_workers, runner="direct")
        batch_no, num_batches = batch.rank
        self._f_ext = f".{num_batches}.{batch_no}"

    @property
    def tc_done_file(self) -> str:
        return os.path.join(self.session.dotdir, self._tc_done_file + self._f_ext)

    @property
    def tc_prog_file(self) -> str:
        return os.path.join(self.session.dotdir, self._tc_prog_file + self._f_ext)


def _setup_individual_case(case, exec_root, copy_all_resources):
    tty.verbose(f"Setting up {case}")
    case.setup(exec_root=exec_root, copy_all_resources=copy_all_resources)
    tty.verbose(f"Done etting up {case}")
    return (case.fullname, vars(case))
