import os
import subprocess
import time
from datetime import datetime
from io import StringIO
from typing import Any
from typing import Optional
from typing import Union

from _nvtest import config
from _nvtest.resources import calculate_allocations
from _nvtest.test.batch import BatchRunner
from _nvtest.test.case import TestCase
from _nvtest.util import logging
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import getuser
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import set_executable
from _nvtest.util.time import hhmmss


class Flux(BatchRunner):
    """Setup and submit jobs to the Flux scheduler"""

    shell = "/bin/sh"
    command_name = "flux"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        batch_no: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("flux runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(cases, batch_no, nbatches, lot_no=lot_no)

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        return name is not None and name.lower() == "flux"

    @property
    def cpus(self) -> int:
        return 1

    @property
    def gpus(self) -> int:
        return 0

    def write_submission_script(self, *args_in: str, **kwargs: Any) -> str:
        """Write the flux submission script"""
        ns = calculate_allocations(self.max_cpus_required)
        timeoutx = kwargs.get("timeoutx", 1.0)
        qtime = self.qtime(minutes=True) * timeoutx

        workers = kwargs.get("workers", ns.cores_per_node)
        session_cpus = ns.nodes * ns.cores_per_node

        args = list(self.default_args)
        args.extend(args_in)
        args.append(f"--nodes={ns.nodes}")
        args.append(f"--time-limit={qtime}")
        args.append(f"--output={self.logfile()}")
        args.append(f"--error={self.logfile()}")

        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        for arg in args:
            fh.write(f"#FLUX: {arg}\n")

        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# batch {self.batch_no} of {self.nbatches}\n")
        fh.write(f"# approximate runtime: {hhmmss(qtime)}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        self.dump_variables(fh)
        invocation = self.nvtest_invocation(workers=workers, cpus=session_cpus, timeoutx=timeoutx)
        fh.write(f"(\n  {invocation}\n)\n")
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f

    def _run(self, *args_in: str, **kwargs: Any) -> None:
        script = self.write_submission_script(*args_in, **kwargs)
        if not os.path.exists(script):
            raise ValueError("submission script not found, did you call setup()?")
        args = [self.command, "batch", "--job-name", self.name, script]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = p.communicate()
        result = str(out.decode("utf-8")).strip()
        parts = result.split()
        if len(parts) == 1 and parts[0]:
            jobid = parts[0]
        else:
            logging.error(f"Failed to find jobid for batch {self.batch_no}/{self.nbatches}")
            logging.log(
                logging.ERROR,
                f"    The following output was received from {self.command}:",
                prefix=None,
            )
            for line in result.split("\n"):
                logging.log(logging.ERROR, f"    {line}", prefix=None)
            return
        logging.debug(f"Submitted batch with jobid={jobid}")

        time.sleep(1)
        running = False
        try:
            while True:
                state = self.poll(jobid)
                if state is None:
                    return
                if not running and state.lower() == "run":
                    if config.get("option:r") == "v":
                        logging.emit(f"STARTING: Batch {self.batch_no} of {self.nbatches}\n")
                    running = True
                time.sleep(0.5)
        except BaseException as e:
            logging.warning(f"cancelling flux job {jobid}")
            self.cancel(jobid)
            if isinstance(e, KeyboardInterrupt):
                return
            raise

    def poll(self, jobid: str) -> Optional[str]:
        flux = Executable("flux")
        result = flux("jobs", "--no-header", "--format={id} {state}", output=str)
        lines = [line.strip() for line in result.get_output().splitlines() if line.split()]
        for line in lines:
            # Output of flux jobs is something like:
            # ID RUN
            parts = line.split()
            if len(parts) == 2:
                jid, state = parts[0], parts[4]
                if jid == jobid:
                    return state
        return None

    def cancel(self, jobid: str) -> None:
        flux = Executable("flux")
        flux("cancel", jobid)
