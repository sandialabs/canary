import json
import os
import sys
from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from typing import Any
from typing import TextIO

from ..test.enums import Result
from ..test.enums import Skip
from ..test.partition import Partition
from ..test.partition import dump_partition
from ..test.testcase import TestCase
from ..util import tty
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import set_executable
from ..util.filesystem import which
from ..util.tty.color import colorize
from .base import Runner


class BatchRunner(Runner):
    shell = "/bin/sh"
    command = "/bin/sh"

    def __init__(self, machine_config: SimpleNamespace, *args: Any):
        super().__init__(machine_config, *args)
        self._dotdir = None

    @property
    def dotdir(self):
        """Find the session's dotdir.  We'd prefer to pass the session to this
        object so that we would not have to infer its location - but that leads
        to incompatibilities with ProcessPoolExecutor"""
        from ..session import Session

        if self._dotdir is None:
            path = os.getcwd()
            while True:
                if Session.is_workdir(path):
                    self._dotdir = os.path.join(path, ".nvtest")
                    break
                path = os.path.dirname(path)
                if path == "/":
                    raise ValueError("Could not find dotdir")
        return self._dotdir

    @staticmethod
    def print_text(text: str):
        sys.stdout.write(f"{text}\n")

    def __call__(self, batch: Partition, *args: Any) -> dict[str, dict]:
        batch_no, num_batches = batch.rank
        self.print_text(f"STARTING: Batch {batch_no + 1} of {num_batches}")
        level = tty.set_log_level(0)
        script = self.write_submission_script(batch)
        script_x = Executable(self.command)
        script_x(script, fail_on_error=False)
        out = os.path.join(self.dotdir, f"testcases.json.{num_batches}.{batch_no}")
        if not os.path.isfile(out):
            tty.error(f"Required output file {out} not found")
            attrs: dict[str, dict] = {}
            for case in batch:
                result = Result(
                    "fail",
                    reason=f"{self.command} failure, required output {out!r} not found",
                )
                attrs[case.fullname] = {"result": result}
                tty.error(result.reason)
            return attrs
        with open(out) as fh:
            results = json.load(fh)
        executed = {}
        for kwds in results:
            tc = TestCase.from_dict(kwds)
            executed[tc.fullname] = tc
        attrs = {}
        for original in batch:
            if original.fullname not in executed:
                case = original
                case.result = Result(
                    "fail", f"Test case {case} not found batch {batch_no}'s output"
                )
                tty.error(case.result.reason)
            else:
                case = executed[original.fullname]
            if case.result == Result.SKIP:
                case.skip = Skip("runtime exception")
            attrs[case.fullname] = vars(case)
        stat: dict[str, int] = {}
        for case in executed.values():
            stat[case.result.name] = stat.get(case.result.name, 0) + 1
        fmt = "@%s{%d %s}"
        st_stat = ", ".join(
            colorize(fmt % (Result.colors[n], v, n)) for (n, v) in stat.items()
        )
        tty.set_log_level(level)
        self.print_text(f"FINISHED: Batch {batch_no + 1} of {num_batches}, {st_stat}")
        #        for (_, func) in plugin.plugins("test", "teardown"):
        #            func(case)
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

    def write_body(self, input_file: str, fh: TextIO) -> None:
        py = sys.executable
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(
            f"{py} -m nvtest -qqq run-batch --concurrent-tests=1 -x {input_file}\n"
        )

    def submit_filename(self, num_batches: int, batch_no: int) -> str:
        basename = f"submit.sh.{num_batches}.{batch_no}"
        return os.path.join(self.dotdir, basename)

    def write_submission_script(self, batch: Partition) -> str:
        batch_no, num_batches = batch.rank
        batch_file = self._dump_batch(batch)
        fh = StringIO()
        self.write_header(fh)
        self.write_body(batch_file, fh)
        f = self.submit_filename(num_batches, batch_no)
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f

    def _dump_batch(self, batch: Partition) -> str:
        batch_no, num_batches = batch.rank
        basename = f"batch.json.{num_batches}.{batch_no}"
        f = os.path.join(self.dotdir, basename)
        with open(f, "w") as fh:
            dump_partition(batch, fh)
        return f

    def max_tasks_required(self, batch: Partition) -> int:
        return max([case.size for case in batch])
