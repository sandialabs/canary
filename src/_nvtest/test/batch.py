import io
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
from ..test.status import Status
from ..third_party.color import colorize
from ..util import logging
from ..util import partition
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import mkdirp
from ..util.filesystem import set_executable
from ..util.time import hhmmss
from .case import TestCase
from .runner import Runner


class Batch(Runner):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch
      runner: How to run this batch
      id: The index of this partition in the group
      nbatches: The number of partitions in the group
      lot_no: The lot number of the group

    """

    shell = "/bin/sh"
    command = "/bin/sh"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        id: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        super().__init__()
        self.validate(cases)
        self.cases = list(cases)
        self.id = id
        self.nbatches = nbatches
        self.lot_no = lot_no
        # self.id: str = hashit("".join(_.id for _ in self), length=20)
        self._status = Status("created")
        first = next(iter(cases))
        self.root = first.exec_root
        self.total_duration: float = -1
        self.max_cpus_required = max([case.processors for case in self.cases])
        self.max_gpus_required = max([case.gpus for case in self.cases])
        self._runtime: float
        if len(self.cases) == 1:
            self._runtime = self.cases[0].runtime
        else:
            ns = calculate_allocations(self.max_cpus_required)
            grid = partition.tile(self.cases, ns.cores_per_node * ns.nodes)
            self._runtime = sum([max(case.runtime for case in row) for row in grid])

    def __iter__(self):
        return iter(self.cases)

    def __len__(self):
        return len(self.cases)

    @property
    def variables(self) -> dict[str, str]:
        return {
            "NVTEST_BATCH_ID": str(self.id),
            "NVTEST_NBATCHES": str(self.nbatches),
            "NVTEST_BATCH_LOT": str(self.lot_no),
            "NVTEST_LEVEL": "2",
            "NVTEST_DISABLE_KB": "1",
        }

    def validate(self, cases: Union[list[TestCase], set[TestCase]]):
        errors = 0
        for case in cases:
            if case.mask:
                logging.fatal(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.mask:
                    errors += 1
                    logging.fatal(f"{dep}: dependent of {case} is masked")
        if errors:
            raise ValueError("Stopping due to previous errors")

    @property
    def cputime(self) -> float:
        return sum(case.processors * min(case.runtime, 5.0) for case in self) * 1.5

    @property
    def runtime(self) -> float:
        return self._runtime

    @property
    def has_dependencies(self) -> bool:
        return any(case.dependencies for case in self.cases)

    @property
    def processors(self) -> int:
        return self.max_cpus_required

    @property
    def gpus(self) -> int:
        return self.max_gpus_required

    @property
    def status(self) -> Status:
        if self._status.value == "pending":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            pending = 0
            for case in self.cases:
                for dep in case.dependencies:
                    if dep.status.value in ("created", "pending", "ready", "running"):
                        pending += 1
            if not pending:
                self._status.set("ready")
        return self._status

    @status.setter
    def status(self, arg: Union[Status, list[str]]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg[0], details=arg[1])

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    @property
    def stage(self):
        return os.path.join(self.root, ".nvtest/batches", str(self.lot_no))

    def submission_script_filename(self) -> str:
        basename = f"submit.{self.nbatches}.{self.id}.sh"
        return os.path.join(self.stage, basename)

    def logfile(self) -> str:
        basename = f"out.{self.nbatches}.{self.id}.txt"
        return os.path.join(self.stage, basename)

    def setup(self) -> None:
        for case in self.cases:
            if any(dep not in self.cases for dep in case.dependencies):
                self._status.set("pending")
                break
        else:
            self._status.set("ready")

    def _run(self, *args: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def start_msg(self) -> str:
        n = len(self.cases)
        return f"SUBMITTING: Batch {self.id} of {self.nbatches} ({n} tests)"

    def end_msg(self) -> str:
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        fmt = "@%s{%d %s}"
        colors = Status.colors
        st_stat = ", ".join(colorize(fmt % (colors[n], v, n)) for (n, v) in stat.items())
        duration: Optional[float] = self.total_duration if self.total_duration > 0 else None
        s = io.StringIO()
        s.write(f"FINISHED: Batch {self.id} of {self.nbatches}, {st_stat} ")
        s.write(f"(time: {hhmmss(duration, threshold=0)}")
        if any(_.start > 0 for _ in self) and any(_.finish > 0 for _ in self):
            ti = min(_.start for _ in self if _.start > 0)
            tf = max(_.finish for _ in self if _.finish > 0)
            s.write(f", running: {hhmmss(tf - ti, threshold=0)}")
            if duration:
                qtime = max(duration - (tf - ti), 0)
                s.write(f", queued: {hhmmss(qtime, threshold=0)}")
        s.write(")")
        return s.getvalue()

    def run(self, *args: str, **kwargs: Any) -> None:
        try:
            start = time.monotonic()
            self._run(*args, **kwargs)
        finally:
            self.total_duration = time.monotonic() - start
            self.refresh()
            for case in self:
                if case.status == "ready":
                    case.status.set("failed", "case failed to start")
                    case.save()
                elif case.status == "running":
                    case.status.set("cancelled", "batch cancelled")
                    case.save()
        return


class SubShell(Batch):
    """Run the Batch in a subshell"""

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        id: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        super().__init__(cases, id, nbatches, lot_no=lot_no)
        self.qtime = self.runtime * 1.5

    def _run(self, *args: str, **kwargs: Any) -> None:
        script = self.write_submission_script(*args, **kwargs)
        if not os.path.exists(script):
            raise ValueError("submission script not found, did you call setup()?")
        script_x = Executable(self.command)
        f = os.path.splitext(script.replace("/submit.", "/out."))[0] + ".txt"
        with open(f, "w") as fh:
            if config.get("option:r") == "v":
                logging.emit(f"STARTING: Batch {self.id} of {self.nbatches}\n")
            script_x(script, fail_on_error=False, output=fh, error=fh)
        return None

    def write_submission_script(self, *args: str, **kwargs: Any) -> str:
        dbg_flag = "-d" if config.get("config:debug") else ""
        timeoutx = kwargs.get("timeoutx", 1.0)
        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# approximate runtime: {hhmmss(self.qtime * timeoutx)}\n")
        fh.write(f"# batch {self.id} of {self.nbatches}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        for var, val in self.variables.items():
            fh.write(f"export {var}={val}\n")
        workers = kwargs.get("workers", 1)
        cpu_ids = ",".join(str(_) for _ in self.cpu_ids)
        fh.write(
            f"(\n  nvtest -d {dbg_flag} -C {self.root} run -rv "
            f"-l session:workers={workers} "
            f"-l session:cpu_ids={cpu_ids} "
            f"-l test:timeoutx={timeoutx} "
            f"^{self.lot_no}:{self.id}\n)\n"
        )
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f


class Slurm(Batch):
    """Setup and submit jobs to the slurm scheduler"""

    name = "slurm"
    shell = "/bin/sh"
    command = "sbatch"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        id: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("slurm runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(cases, id, nbatches, lot_no=lot_no)

    @property
    def processors(self) -> int:
        return 1

    @property
    def gpus(self) -> int:
        return 0

    def _run(self, *args_in: str, **kwargs: Any) -> None:
        script = self.write_submission_script(*args_in, **kwargs)
        if not os.path.exists(script):
            raise ValueError("submission script not found, did you call setup()?")
        args = [self.command, script]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = p.communicate()
        result = str(out.decode("utf-8")).strip()
        i = result.find("Submitted batch job")
        if i >= 0:
            parts = result[i:].split()
            if len(parts) > 3 and parts[3]:
                jobid = parts[3]
        else:
            logging.error(f"Failed to find jobid for batch {self.id}/{self.nbatches}")
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
                        logging.emit(f"STARTING: Batch {self.id} of {self.nbatches}\n")
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

    @property
    def qtime(self) -> float:
        if len(self.cases) == 1:
            return self.cases[0].timeout
        total_runtime = self.runtime
        if total_runtime < 100.0:
            total_runtime = 300.0
        elif total_runtime < 300.0:
            total_runtime = 600.0
        elif total_runtime < 600.0:
            total_runtime = 1200.0
        elif total_runtime < 1800.0:
            total_runtime = 2400.0
        elif total_runtime < 3600.0:
            total_runtime = 5000.0
        else:
            total_runtime *= 1.1
        return total_runtime

    def write_submission_script(self, *args_in: str, **kwargs: Any) -> str:
        ns = calculate_allocations(self.max_cpus_required)
        timeoutx = kwargs.get("timeoutx", 1.0)
        qtime = self.qtime * timeoutx

        workers = kwargs.get("workers", ns.cores_per_node)
        session_cpus = ns.nodes * ns.cores_per_node
        tpn = int(ns.cores_per_node / ns.cpus_per_task if workers > 1 else ns.tasks_per_node)

        args = list(args_in)
        args.append(f"--nodes={ns.nodes}")
        args.append(f"--ntasks-per-node={tpn}")
        args.append(f"--cpus-per-task={ns.cpus_per_task}")
        args.append(f"--time={hhmmss(qtime * 1.25, threshold=0)}")
        file = self.logfile()
        args.append(f"--error={file}")
        args.append(f"--output={file}")

        dbg_flag = "-d" if config.get("config:debug") else ""
        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        for arg in args:
            fh.write(f"#SBATCH {arg}\n")
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# batch {self.id} of {self.nbatches}\n")
        fh.write(f"# approximate runtime: {hhmmss(qtime)}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        for var, val in self.variables.items():
            fh.write(f"export {var}={val}\n")
        fh.write(f"(\n  nvtest {dbg_flag} -C {self.root} run -rv ")
        fh.write(f"-l session:workers={workers} ")
        fh.write(f"-l session:cpu_count={session_cpus} ")
        fh.write(f"-l test:timeoutx={timeoutx} ")
        fh.write(f"^{self.lot_no}:{self.id}\n)\n")
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f

    def poll(self, jobid: str) -> Optional[str]:
        squeue = Executable("squeue")
        out = squeue("--noheader", "-o", "%i %t", output=str)
        for line in out.splitlines():
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


class PBS(Batch):
    """Setup and submit jobs to the PBS scheduler"""

    name = "pbs"
    shell = "/bin/sh"
    command = "qsub"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        id: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("slurm runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(cases, id, nbatches, lot_no=lot_no)

    @property
    def processors(self) -> int:
        return 1

    @property
    def gpus(self) -> int:
        return 0

    def write_submission_script(self, *args_in: str, **kwargs: Any) -> str:
        """Write the pbs submission script"""
        ns = calculate_allocations(self.max_cpus_required)
        timeoutx = kwargs.get("timeoutx", 1.0)
        qtime = self.qtime * timeoutx
        dbg_flag = "-d" if config.get("config:debug") else ""
        workers = kwargs.get("workers", ns.cores_per_node)
        session_cpus = ns.nodes * ns.cores_per_node
        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        fh.write(f"#PBS -l nodes={ns.nodes}:ppn={ns.cores_per_node}")
        fh.write(f"#PBS -l walltime={hhmmss(qtime)}\n")
        fh.write("#PBS -j oe\n")
        fh.write(f"#PBS -o {self.logfile()}\n")
        for arg in args_in:
            fh.write(f"#PBS {arg}\n")
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# batch {self.id} of {self.nbatches}\n")
        fh.write(f"# approximate runtime: {hhmmss(qtime)}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        for var, val in self.variables.items():
            fh.write(f"export {var}={val}\n")
        fh.write(
            f"(\n  nvtest {dbg_flag} -C {self.root} run -rv "
            f"-l session:workers={workers} "
            f"-l session:cpu_count={session_cpus} "
            f"-l test:timeoutx={timeoutx} "
            f"^{self.lot_no}:{self.id}\n)\n"
        )
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return f

    @property
    def qtime(self) -> float:
        if len(self.cases) == 1:
            return self.cases[0].timeout
        total_runtime = self.runtime
        if total_runtime < 100.0:
            total_runtime = 300.0
        elif total_runtime < 300.0:
            total_runtime = 600.0
        elif total_runtime < 600.0:
            total_runtime = 1200.0
        elif total_runtime < 1800.0:
            total_runtime = 2400.0
        elif total_runtime < 3600.0:
            total_runtime = 5000.0
        else:
            total_runtime *= 1.1
        return total_runtime

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
            logging.error(f"Failed to find jobid for batch {self.id}/{self.nbatches}")
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
                        logging.emit(f"STARTING: Batch {self.id} of {self.nbatches}\n")
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
        out = qstat(output=str)
        lines = [line.strip() for line in out.splitlines() if line.split()]
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


def factory(
    cases: Union[list[TestCase], set[TestCase]],
    id: int,
    nbatches: int,
    lot_no: int = 1,
    scheduler: Optional[str] = None,
) -> Batch:
    batch: Batch
    if scheduler in (None, "shell", "subshell"):
        batch = SubShell(cases, id, nbatches, lot_no)
    elif scheduler and scheduler.lower() == "slurm":
        batch = Slurm(cases, id, nbatches, lot_no)
    else:
        raise ValueError(f"{scheduler}: Unknown batch scheduler")
    batch.setup()
    return batch
