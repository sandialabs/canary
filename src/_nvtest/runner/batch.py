import os
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from .. import config
from ..test.partition import Partition
from ..test.status import Status
from ..util import logging
from ..util.color import colorize
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import mkdirp
from ..util.filesystem import set_executable
from ..util.filesystem import which
from .base import Runner

if TYPE_CHECKING:
    from _nvtest.session import Session


class BatchRunner(Runner):
    shell = "/bin/sh"
    command = "/bin/sh"

    def __init__(self, session: "Session", **kwargs: Any) -> None:
        super().__init__(session, **kwargs)
        self.options: list[str] = [str(_) for _ in kwargs.get("options") or []]

    def setup(self, batch: Partition) -> None:
        self.write_submission_script(batch)

    def avail_workers(self, batch: Partition) -> int:
        return 1

    def calculate_resource_allocations(self, batch: Partition) -> None: ...

    def run(self, batch: Partition, **kwds: Any) -> dict[str, dict]:
        n = len(batch)
        logging.emit(
            f"SUBMITTING: Batch {batch.world_rank + 1} of {batch.world_size} ({n} tests)"
        )
        script = self.submit_filename(batch)
        if not os.path.exists(script):
            self.write_submission_script(batch)
        try:
            script_x = Executable(self.command)
            if self.default_args:
                script_x.add_default_args(*self.default_args)
            f = self.logfile(batch)
            mkdirp(os.path.dirname(f))
            with open(f, "w") as fh:
                script_x(script, fail_on_error=False, output=fh, error=fh)
        finally:
            self.load_batch_results(batch)
            stat: dict[str, int] = {}
            attrs: dict[str, dict] = {}
            for case in batch:
                stat[case.status.value] = stat.get(case.status.value, 0) + 1
                data = {
                    "start": case.start,
                    "finish": case.finish,
                    "status": [case.status.value, case.status.details],
                }
                attrs[case.fullname] = data
            fmt = "@%s{%d %s}"
            st_stat = ", ".join(
                colorize(fmt % (Status.colors[n], v, n)) for (n, v) in stat.items()
            )
            logging.emit(
                f"FINISHED:   Batch {batch.world_rank + 1} of {batch.world_size}, {st_stat}"
            )
        return attrs

    @classmethod
    def validate(cls, items):
        x = which(cls.command)
        if x is None:
            raise ValueError(f"Required command {cls.command} not found")
        if not isinstance(items, list) and not isinstance(items[0], Partition):
            s = f"{items.__class__.__name__}"
            raise ValueError(f"{cls.__name__} is only compatible with list[Partition], not {s}")

    def write_header(self, fh: TextIO, batch: Partition) -> None:
        raise NotImplementedError

    def write_body(self, batch: Partition, fh: TextIO) -> None:
        max_test_cpus = self.max_tasks_required(batch)
        max_workers = self.avail_workers(batch)
        session_cpus = max(max_workers, max_test_cpus)
        dbg_flag = "-d" if config.get("config:debug") else ""
        fh.write(
            f"(\n  nvtest {dbg_flag} -C {self.work_tree} run "
            f"-l session:workers:{max_workers} "
            f"-l session:cpus:{session_cpus} "
            f"-l test:cpus:{max_test_cpus} "
            f"^{batch.world_id}:{batch.world_rank}\n)\n"
        )

    def submit_filename(self, batch: Partition) -> str:
        basename = f"submit.{batch.world_size}.{batch.world_rank}.sh"
        return os.path.join(self.stage, "batch", str(batch.world_id), basename)

    def logfile(self, batch: Partition) -> str:
        basename = f"out.{batch.world_size}.{batch.world_rank}.txt"
        return os.path.join(self.stage, "batch", str(batch.world_id), basename)

    def write_submission_script(self, batch: Partition) -> None:
        self.calculate_resource_allocations(batch)
        fh = StringIO()
        self.write_header(fh, batch)
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# batch {batch.world_rank + 1} of {batch.world_size}\n")
        fh.write("export NVTEST_DISABLE_KB=1\n")
        self.write_body(batch, fh)
        f = self.submit_filename(batch)
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return

    def max_tasks_required(self, batch: Partition) -> int:
        return max([case.processors for case in batch])

    def load_batch_results(self, batch: Partition):
        """Load the results for cases in this batch

        Batches are run in a subprocess and the results written to

        $work_tree/.nvtest/stage/$session_id/tests

        These results are loaded and assigned to the test cases in *this*
        processes' memory

        """
        for case in batch:
            d = os.path.relpath(case.file_root)
            logging.debug(f"Loading case {case.id} from {d}/{case.file_path}")
            try:
                fd = case.load_results()
            except FileNotFoundError:
                case.status.set(
                    "failed",
                    f"Test case {case} not found in batch {batch.world_rank}'s output",
                )
            else:
                if fd["status"][0] == "staged":
                    # This case was never run
                    case.status.set("notrun", "Batch case not run for unknown reasons")
                    case.dump()
                else:
                    case.update(fd)
