import os
import subprocess
import time
from datetime import datetime
from io import StringIO
from typing import Any
from typing import Optional
from typing import Union

from .. import config
from ..resources import calculate_allocations
from ..test.batch import BatchRunner
from ..test.case import TestCase
from ..util import logging
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import mkdirp
from ..util.filesystem import set_executable
from ..util.time import hhmmss


class PBS(BatchRunner):
    """Setup and submit jobs to the PBS scheduler"""

    shell = "/bin/sh"
    command_name = "qsub"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        batch_no: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("PBS runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(cases, batch_no, nbatches, lot_no=lot_no)

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        return name is not None and name.lower() in ("pbs", PBS.command_name)

    @property
    def cpus(self) -> int:
        return 1

    @property
    def gpus(self) -> int:
        return 0

    def write_submission_script(self, *args_in: str, **kwargs: Any) -> str:
        """Write the pbs submission script"""
        ns = calculate_allocations(self.max_cpus_required)
        timeoutx = kwargs.get("timeoutx", 1.0)
        qtime = self.qtime() * timeoutx

        workers = kwargs.get("workers", ns.cores_per_node)
        session_cpus = ns.nodes * ns.cores_per_node

        args = list(self.default_args)
        args.extend(args_in)
        args.append(f"-l nodes={ns.nodes}:ppn={ns.cores_per_node}")
        args.append(f"-l walltime={hhmmss(qtime * 1.25, threshold=0)}")
        args.append("-j oe")
        args.append(f"-o {self.logfile()}")
        args.append(f"-N {self.name}")

        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        for arg in args:
            fh.write(f"#PBS {arg}\n")

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
        args = [self.command, script]
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
                if not running and state in ("R", "RUNNING"):
                    if config.get("option:r") == "v":
                        logging.emit(f"STARTING: Batch {self.batch_no} of {self.nbatches}\n")
                    running = True
                if state is None:
                    return
                time.sleep(0.5)
        except BaseException as e:
            logging.warning(f"cancelling pbs job {jobid}")
            self.cancel(jobid)
            if isinstance(e, KeyboardInterrupt):
                return
            raise

    def poll(self, jobid: str) -> Optional[str]:
        qstat = Executable("qstat")
        result = qstat(output=str)
        lines = [line.strip() for line in result.get_output().splitlines() if line.split()]
        for line in lines:
            # Output of qstat is something like:
            # Job id            Name             User              Time Use S Queue
            # ----------------  ---------------- ----------------  -------- - -----
            # 9932285.string-*  spam.sh          username                 0 W serial
            parts = line.split()
            if len(parts) >= 6:
                jid, state = parts[0], parts[4]
                if jid == jobid:
                    return state
                elif jid[-1] == "*" and jobid.startswith(jid[:-1]):
                    # the output from qstat may return a truncated job id,
                    # so match the beginning of the incoming 'jobids' strings
                    return state
        return None

    def cancel(self, jobid: str) -> None:
        qdel = Executable("qdel")
        qdel(jobid)
