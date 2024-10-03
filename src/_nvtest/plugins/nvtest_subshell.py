import os
from datetime import datetime
from io import StringIO
from typing import Any
from typing import Optional
from typing import Union

from .. import config
from ..test.batch import BatchRunner
from ..test.case import TestCase
from ..util import logging
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import mkdirp
from ..util.filesystem import set_executable
from ..util.time import hhmmss


class SubShell(BatchRunner):
    """Run the Batch in a subshell"""

    command_name = "sh"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        batch_no: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        super().__init__(cases, batch_no, nbatches, lot_no=lot_no)

    def qtime(self, minutes: bool = False) -> float:
        return self.runtime * 1.5

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        if name is None or name.lower() in ("shell", "subshell"):
            return True
        return False

    def _run(self, *args: str, **kwargs: Any) -> None:
        script = self.write_submission_script(*args, **kwargs)
        if not os.path.exists(script):
            raise ValueError("submission script not found, did you call setup()?")
        script_x = Executable(self.command)
        f = self.logfile()
        with open(f, "w") as fh:
            if config.get("option:r") == "v":
                logging.emit(f"STARTING: Batch {self.batch_no} of {self.nbatches}\n")
            script_x(script, fail_on_error=False, output=fh, error=fh)
        return None

    def write_submission_script(self, *args: str, **kwargs: Any) -> str:
        timeoutx = kwargs.get("timeoutx", 1.0)
        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# approximate runtime: {hhmmss(self.qtime() * timeoutx)}\n")
        fh.write(f"# batch {self.batch_no} of {self.nbatches}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        self.dump_variables(fh)
        workers = kwargs.get("workers", 1)
        invocation = self.nvtest_invocation(workers=workers, timeoutx=timeoutx)
        fh.write(f"(\n  {invocation}\n)\n")
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f
