import errno
import os
import time
from typing import TYPE_CHECKING

from ..executor import SingleBatchDirectExecutor
from ..test.partition import Partition
from ..test.partition import load_partition
from ..util.returncode import compute_returncode
from .common import add_timing_arguments
from .common import add_workdir_arguments
from .run_tests import RunTests

if TYPE_CHECKING:
    from ..config import Config


class RunBatch(RunTests):
    """Run a single batch of tests.  Run nv.test create-batches first"""

    family = "batch"
    batch: Partition

    def __init__(self, *, config: "Config") -> None:
        super(RunTests, self).__init__(config=config)
        if not os.path.exists(self.option.file):
            file = self.option.file
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file)
        self._mode = self.Mode.WRITE
        if self.option.x:
            self._mode = self.Mode.APPEND
            if self.option.workdir is None:
                self.option.workdir = self.find_workdir(
                    start=os.path.dirname(self.option.file)
                )
        self.workdir = self.option.workdir or "./TestResults"
        self.search_paths = []
        self.option.on_options = None
        self.option.keyword_expr = None
        self.runner = "direct"
        self.runner_options = None
        self.batch_size = None

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
        self.print_text(f"work directory: {self.workdir}")
        self.batch = load_partition(self.option.file)
        self.print_text(f"batch {self.batch.rank[0] + 1} of {self.batch.rank[1]}")
        self.cases = [case for case in self.batch]
        self.executor = SingleBatchDirectExecutor(
            self,
            self.batch,
            max_workers=self.option.max_workers,
        )
        if self.mode == self.Mode.WRITE:
            self.executor.setup(copy_all_resources=self.option.copy_all_resources)

    def run(self) -> int:
        self.start = time.time()
        self.executor.run(timeout=self.option.timeout)
        self.finish = time.time()
        return compute_returncode(self.cases)

    @staticmethod
    def setup_parser(parser):
        add_workdir_arguments(parser)
        add_timing_arguments(parser)
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
