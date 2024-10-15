import os
from datetime import datetime
from typing import IO
from typing import Any
from typing import Optional

from _nvtest import config
from _nvtest.runners import BatchRunner
from _nvtest.test.batch import TestBatch
from _nvtest.util import logging
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import getuser
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import set_executable
from _nvtest.util.time import hhmmss


class SubShell(BatchRunner):
    """Run the Batch in a subshell"""

    scheduled = False
    shell = "/bin/sh"
    command_name = "sh"

    def qtime(self, batch: TestBatch, minutes: bool = False) -> float:
        return batch.runtime * 1.5

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        if name is not None and name.lower() in ("shell", "subshell"):
            return True
        return False

    def write_submission_script(self, batch: TestBatch, file: IO[Any]) -> None:
        file.write(f"#!{self.shell}\n")
        file.write(f"# user: {getuser()}\n")
        file.write(f"# date: {datetime.now().strftime('%c')}\n")
        file.write(f"# approximate runtime: {hhmmss(self.qtime(batch) * self.timeoutx)}\n")
        file.write(f"# batch {batch.batch_no} of {batch.nbatches}\n")
        file.write("# test cases:\n")
        for case in batch.cases:
            file.write(f"# - {case.fullname}\n")
        file.write(f"# total: {len(batch.cases)} test cases\n")
        for var, val in batch.variables.items():
            if val is None:
                file.write(f"unset {var}\n")
            else:
                file.write(f"export {var}={val}\n")
        workers = self.workers or 1
        invocation = self.nvtest_invocation(
            batch=batch, workers=workers, cpus=batch.max_cpus_required
        )
        file.write(f"(\n  {invocation}\n)\n")

    def run_batch(self, batch: TestBatch) -> None:
        script = batch.submission_script_filename()
        mkdirp(os.path.dirname(script))
        with open(script, "w") as fh:
            self.write_submission_script(batch, fh)
        set_executable(script)
        script_x = Executable(self.exe)
        f = batch.logfile()
        if config.get("config:debug"):
            logging.debug(f"Starting batch {batch.batch_no} of {batch.nbatches}")
        with open(f, "w") as fh:
            script_x(script, fail_on_error=False, output=fh, error=fh)
        return
