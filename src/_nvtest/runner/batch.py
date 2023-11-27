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

    def __init__(self, session: "Session", *args: Any):
        super().__init__(session, *args)
        self.batchdir = session.batchdir

    @staticmethod
    def print_text(text: str):
        sys.stdout.write(f"{text}\n")

    def __call__(self, batch: Partition, *args: Any) -> dict[str, dict]:
        batch_no, num_batches = batch.rank
        n = len(batch)
        self.print_text(f"STARTING: Batch {batch_no + 1} of {num_batches} ({n} tests)")
        level = tty.set_log_level(0)
        script = self.write_submission_script(batch)
        with tty.restore():
            script_x = Executable(self.command)
            if self.default_args:
                script_x.add_default_args(*self.default_args)
            script_x(script, fail_on_error=False)
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
        tty.set_log_level(level)
        self.print_text(f"FINISHED: Batch {batch_no + 1} of {num_batches}, {st_stat}")
        #        for hook in plugin.plugins("test", "finish"):
        #            hook(case)
        return attrs

    @classmethod
    def validate(cls, items):
        x = which(cls.command)
        if x is None:
            tty.die(f"Required command {cls.command} not found")
        if not isinstance(items, list) and not isinstance(items[0], Partition):
            s = f"{items.__class__.__name__}"
            tty.die(f"{cls.__name__} is only compatible with list[Partition], not {s}")

    def write_header(self, fh: TextIO) -> None:
        raise NotImplementedError

    def write_body(self, batch_no: int, fh: TextIO) -> None:
        py = sys.executable
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"{py} -m nvtest -qqq -C {self.work_tree} run --max-workers=1 ")
        fh.write(f"^b {batch_no} ^s {self.session}\n")

    def submit_filename(self, batch_no: int) -> str:
        n = max(digits(batch_no), 3)
        basename = f"{batch_no:0{n}}.sh"
        return os.path.join(self.batchdir, basename)

    def write_submission_script(self, batch: Partition) -> str:
        batch_no, num_batches = batch.rank
        fh = StringIO()
        self.write_header(fh)
        self.write_body(batch_no, fh)
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
        from .. import session

        fd = session.load_test_results(self.stage)
        for case in batch:
            if case.id not in fd:
                # This should never happen
                case.result = Result(
                    "fail", f"Test case {case} not found batch {batch.rank[0]}'s output"
                )
                tty.error(case.result.reason)
            elif fd[case.id]["result"] == "SETUP":
                # This case was never run
                case.result = Result("NOTDONE", "This case was never run after setup")
            else:
                case.update(fd[case.id])
