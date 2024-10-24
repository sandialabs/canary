import os
import subprocess
import time
from datetime import datetime
from typing import IO
from typing import Any
from typing import Optional

from _nvtest import config
from _nvtest.hpc_scheduler import HPCScheduler
from _nvtest.resource import ResourceHandler
from _nvtest.resource import calculate_allocations
from _nvtest.test.batch import TestBatch
from _nvtest.util import logging
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import getuser
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import set_executable
from _nvtest.util.time import hhmmss


class PBS(HPCScheduler):
    """Setup and submit jobs to the PBS scheduler"""

    shell = "/bin/sh"
    command_name = "qsub"

    def __init__(self, rh: ResourceHandler) -> None:
        super().__init__(rh)
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("pbs runner requires that 'machine:cores_per_socket' be defined")

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        return name is not None and name.lower() in ("pbs", PBS.command_name)

    def write_submission_script(self, batch: TestBatch, file: IO[Any]) -> None:
        """Write the pbs submission script"""
        ns = calculate_allocations(batch.max_cpus_required)
        qtime = self.qtime(batch) * self.timeoutx

        session_cpus = ns.nodes * ns.cores_per_node

        args = list(self.default_args)
        args.extend(self.extra_args)
        args.append(f"-l nodes={ns.nodes}:ppn={ns.cores_per_node}")
        args.append(f"-l walltime={hhmmss(qtime * 1.25, threshold=0)}")
        args.append("-j oe")
        args.append(f"-o {batch.logfile()}")
        args.append(f"-N {batch.name}")

        file.write(f"#!{self.shell}\n")
        for arg in args:
            file.write(f"#PBS {arg}\n")

        file.write(f"# user: {getuser()}\n")
        file.write(f"# date: {datetime.now().strftime('%c')}\n")
        file.write(f"# batch {batch.batch_no} of {batch.nbatches}\n")
        file.write(f"# approximate runtime: {hhmmss(qtime)}\n")
        file.write("# test cases:\n")
        for case in batch.cases:
            file.write(f"# - {case.fullname}\n")
        file.write(f"# total: {len(batch.cases)} test cases\n")
        for var, val in batch.variables.items():
            if val is None:
                file.write(f"unset {var}\n")
            else:
                file.write(f"export {var}={val}\n")
        workers = self.workers or ns.cores_per_node
        invocation = self.nvtest_invocation(batch=batch, workers=workers, cpus=session_cpus)
        file.write(f"(\n  {invocation}\n)\n")

    def submit_and_wait(self, batch: TestBatch) -> None:
        script = batch.submission_script_filename()
        mkdirp(os.path.dirname(script))
        with open(script, "w") as fh:
            self.write_submission_script(batch, fh)
        set_executable(script)
        args = [self.exe, script]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = p.communicate()
        result = str(out.decode("utf-8")).strip()
        parts = result.split()
        if len(parts) == 1 and parts[0]:
            jobid = parts[0]
        else:
            logging.error(f"Failed to find jobid for batch {batch.batch_no}/{batch.nbatches}")
            logging.log(
                logging.ERROR,
                f"    The following output was received from {self.exe}:",
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
                    logging.debug(f"Starting batch {batch.batch_no} of {batch.nbatches}")
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
