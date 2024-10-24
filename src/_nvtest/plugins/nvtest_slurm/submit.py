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


class Slurm(HPCScheduler):
    """Setup and submit jobs to the slurm scheduler"""

    shell = "/bin/sh"
    command_name = "sbatch"

    def __init__(self, rh: ResourceHandler) -> None:
        super().__init__(rh)
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("slurm runner requires that 'machine:cores_per_socket' be defined")

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        return name is not None and name.lower() in ("slurm", Slurm.command_name)

    def write_submission_script(self, batch: TestBatch, file: IO[Any]) -> None:
        ns = calculate_allocations(batch.max_cpus_required)
        qtime = self.qtime(batch) * self.timeoutx
        session_cpus = ns.nodes * ns.cores_per_node
        workers = self.workers or ns.cores_per_node
        tpn = int(ns.cores_per_node / ns.cpus_per_task if workers > 1 else ns.tasks_per_node)

        args = list(self.default_args)
        args.extend(self.extra_args)
        args.append(f"--nodes={ns.nodes}")
        args.append(f"--ntasks-per-node={tpn}")
        args.append(f"--cpus-per-task={ns.cpus_per_task}")
        args.append(f"--time={hhmmss(qtime * 1.25, threshold=0)}")
        args.append(f"--job-name={batch.name}")
        f = batch.logfile()
        args.append(f"--error={f}")
        args.append(f"--output={f}")

        file.write(f"#!{self.shell}\n")
        for arg in args:
            file.write(f"#SBATCH {arg}\n")
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
        invocation = self.nvtest_invocation(batch=batch, workers=workers, cpus=session_cpus)
        file.write(f"(\n  {invocation}\n)\n")
        return

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
        i = result.find("Submitted batch job")
        if i >= 0:
            parts = result[i:].split()
            if len(parts) > 3 and parts[3]:
                jobid = parts[3]
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
            logging.warning(f"cancelling sbatch job {jobid}")
            self.cancel(jobid)
            if isinstance(e, KeyboardInterrupt):
                return
            raise

    def poll(self, jobid: str) -> Optional[str]:
        squeue = Executable("squeue")
        result = squeue("--noheader", "-o", "%i %t", output=str)
        for line in result.get_output().splitlines():
            # a line should be something like "16004759 PD"
            try:
                id, state = line.split()
            except ValueError:
                continue
            if id == jobid:
                return state
        return None

    def cancel(self, jobid: str) -> None:
        scancel = Executable("scancel")
        scancel(jobid, "--clusters=all")
