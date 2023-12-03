import os
import sys
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from ..test.enums import Result
from ..test.partition import Partition
from ..util import tty
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import set_executable
from ..util.filesystem import which
from ..util.misc import digits
from ..util.tty.color import colorize
from .base import Runner

if TYPE_CHECKING:
    from _nvtest.session import Session


class BatchRunner(Runner):
    shell = "/bin/sh"
    command = "/bin/sh"

    def __init__(self, session: "Session", *args: Any) -> None:
        super().__init__(session, *args)
        self.batchdir = session.batchdir

    @staticmethod
    def print_text(text: str):
        sys.stdout.write(f"{text}\n")

    def run(self, batch: Partition, **kwargs: Any) -> dict[str, dict]:
        batch_no, num_batches = batch.rank
        n = len(batch)
        self.print_text(f"STARTING: Batch {batch_no + 1} of {num_batches} ({n} tests)")
        script = self.write_submission_script(batch)
        with tty.restore():
            script_x = Executable(self.command)
            if self.default_args:
                script_x.add_default_args(*self.default_args)
            with open(self.logfile(batch_no), "w") as fh:
                script_x(script, fail_on_error=False, output=fh, error=fh)
        self.load_batch_results(batch)
        stat: dict[str, int] = {}
        attrs: dict[str, dict] = {}
        for case in batch:
            stat[case.result.name] = stat.get(case.result.name, 0) + 1
            data = {
                "start": case.start,
                "finish": case.finish,
                "result": [case.result.name, case.result.reason],
            }
            attrs[case.fullname] = data
        fmt = "@%s{%d %s}"
        st_stat = ", ".join(
            colorize(fmt % (Result.colors[n], v, n)) for (n, v) in stat.items()
        )
        self.print_text(f"FINISHED: Batch {batch_no + 1} of {num_batches}, {st_stat}")
        #        for hook in plugin.plugins("test", "finish"):
        #            hook(case)
        return attrs

    @classmethod
    def validate(cls, items):
        x = which(cls.command)
        if x is None:
            raise ValueError(f"Required command {cls.command} not found")
        if not isinstance(items, list) and not isinstance(items[0], Partition):
            s = f"{items.__class__.__name__}"
            raise ValueError(
                f"{cls.__name__} is only compatible with list[Partition], not {s}"
            )

    def write_header(self, fh: TextIO) -> None:
        raise NotImplementedError

    def write_body(self, batch: Partition, fh: TextIO) -> None:
        batch_no, num_batches = batch.rank
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# batch {batch_no + 1} of {num_batches}\n")
        fh.write("(\n  export NVTEST_DISABLE_KB=1\n")
        fh.write(f"  nvtest -C {self.work_tree} run --max-workers=1 ^{batch_no}\n)\n")

    def submit_filename(self, batch_no: int) -> str:
        n = max(digits(batch_no), 3)
        basename = f"{batch_no:0{n}}.sh"
        return os.path.join(self.batchdir, basename)

    def logfile(self, batch_no: int) -> str:
        n = max(digits(batch_no), 3)
        basename = f"{batch_no:0{n}}.log"
        return os.path.join(self.batchdir, basename)

    def write_submission_script(self, batch: Partition) -> str:
        batch_no, _ = batch.rank
        fh = StringIO()
        self.write_header(fh)
        self.write_body(batch, fh)
        f = self.submit_filename(batch_no)
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f

    def max_tasks_required(self, batch: Partition) -> int:
        return max([case.size for case in batch])

    def load_batch_results(self, batch: Partition):
        """Load the results for cases in this batch

        Batches are run in a subprocess and the results written to

        $work_tree/.nvtest/stage/$session_id/tests

        These results are loaded and assigned to the test cases in *this*
        processes' memory

        """
        for case in batch:
            try:
                fd = case.load_results()
            except FileNotFoundError:
                case.result = Result(
                    "fail", f"Test case {case} not found batch {batch.rank[0]}'s output"
                )
            else:
                if fd["result"] == "SETUP":
                    # This case was never run
                    case.result = Result("NOTDONE", "Case never run after setup")
                else:
                    case.update(fd)
