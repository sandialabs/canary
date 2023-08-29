import argparse
import errno
import os
import time
from typing import TYPE_CHECKING

from _nvtest.executor import SingleBatchDirectExecutor
from _nvtest.test.partition import Partition
from _nvtest.test.partition import load_partition
from _nvtest.util.returncode import compute_returncode
from _nvtest.util.time import time_in_seconds

from .run_tests import RunTests

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session


class RunBatch(RunTests):
    name = "run-batch"
    description = "Run a single batch of tests.  Run nv.test create-batches first"
    batch: Partition

    def __init__(self, config: "Config", session: "Session") -> None:
        self.config = config
        self.session = session
        if not os.path.exists(self.session.option.file):
            file = self.session.option.file
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file)
        self._mode = "write"
        if self.session.option.x:
            self._mode = "append"
            if self.session.option.workdir is None:
                self.session.option.workdir = self.find_workdir(
                    start=os.path.dirname(self.session.option.file)
                )
        self.search_paths = []
        self.option = argparse.Namespace(
            on_options=None,
            keyword_expr=None,
            timeout=self.session.option.timeout,
            max_workers=self.session.option.max_workers,
            copy_all_resources=self.session.option.copy_all_resources,
            runner="direct",
            runner_options=None,
            batch_size=None,
        )

    @staticmethod
    def find_workdir(start) -> str:
        path = start
        while True:
            f = os.path.join(path, ".nvtest/session.json")
            if os.path.exists(f):
                return path
            path = os.path.dirname(path)
            if path == "/":
                raise ValueError("Could not find workdir")

    @property
    def mode(self):
        return self._mode

    def setup(self):
        self.print_section_header("Beginning test session")
        self.print_front_matter()
        self.print_text(f"work directory: {self.session.workdir}")
        self.batch = load_partition(self.session.option.file)
        self.print_text(f"batch {self.batch.rank[0] + 1} of {self.batch.rank[1]}")
        self.cases = [case for case in self.batch]
        self.executor = SingleBatchDirectExecutor(
            self.session,
            self.batch,
            max_workers=self.option.max_workers,
        )
        if self.session.mode == self.session.Mode.WRITE:
            self.executor.setup(copy_all_resources=self.option.copy_all_resources)

    def run(self) -> int:
        start = time.time()
        self.executor.run(timeout=self.option.timeout)
        finish = time.time()
        duration = finish - start
        self.print_test_results_summary(duration)
        return compute_returncode(self.cases)

    @staticmethod
    def add_options(parser):
        parser.add_argument(
            "--timeout",
            type=time_in_seconds,
            default=60 * 60,
            help="Set a timeout on test execution [default: 1 hr]",
        )
        parser.add_argument(
            "--concurrent-tests",
            type=int,
            dest="max_workers",
            default=-1,
            help="Number of concurrent tests to run.  "
            "-1 determines the concurrency automatically [default: %(default)s]",
        )
        parser.add_argument(
            "-x",
            action="store_true",
            help="This batch is setup, just run it [default: %(default)s]",
        )
        parser.add_argument(
            "--copy-all-resources",
            action="store_true",
            help="Do not link resources to the test "
            "directory, only copy [default: %(default)s]",
        )
        parser.add_argument("file", help="Batch file")
