import os
import subprocess
import time
from datetime import datetime
from io import StringIO
from typing import Any
from typing import Optional
from typing import Union

from .. import config
from ..test.status import Status
from ..third_party.color import colorize
from ..util import logging
from ..util.executable import Executable
from ..util.filesystem import getuser
from ..util.filesystem import mkdirp
from ..util.filesystem import set_executable
from ..util.hash import hashit
from ..util.resource import calculate_allocations
from ..util.time import hhmmss
from .case import TestCase
from .runner import Runner


class Batch(Runner):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch
      runner: How to run this batch
      world_rank: The index of this partition in the group
      world_size: The number of partitions in the group
      world_id: The id of the group

    """

    shell = "/bin/sh"
    command = "/bin/sh"

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        world_rank: int,
        world_size: int,
        world_id: int = 1,
    ) -> None:
        self.cases = cases
        self.world_rank = world_rank
        self.world_size = world_size
        self.world_id = world_id
        self.id: str = hashit("".join(_.id for _ in self), length=20)
        self._status = Status("created")
        first = next(iter(cases))
        self.root = first.exec_root

    def __iter__(self):
        return iter(self.cases)

    def __len__(self):
        return len(self.cases)

    @property
    def processors(self) -> int:
        return max(case.processors for case in self if not case.masked)

    @property
    def devices(self) -> int:
        return max(case.devices for case in self if not case.masked)

    @property
    def cputime(self) -> float:
        return sum(case.processors * case.runtime for case in self if not case.masked)

    @property
    def runtime(self) -> float:
        return sum(case.runtime for case in self if not case.masked)

    @property
    def has_dependencies(self) -> bool:
        return any(case.dependencies for case in self.cases)

    @property
    def status(self) -> Status:
        if self._status.value == "pending":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            external_deps = [d for c in self.cases for d in c.dependencies if d not in self.cases]
            stat = [dep.status.value for dep in external_deps]
            if all([_ in ("success", "diffed") for _ in stat]):
                self._status.set("ready")
            elif any([_ == "skipped" for _ in stat]):
                self._status.set("skipped", "one or more dependency was skipped")
            elif any([_ == "cancelled" for _ in stat]):
                self._status.set("skipped", "one or more dependency was cancelled")
            elif any([_ == "timeout" for _ in stat]):
                self._status.set("skipped", "one or more dependency timed out")
            elif any([_ == "failed" for _ in stat]):
                self._status.set("skipped", "one or more dependency failed")
        return self._status

    @status.setter
    def status(self, arg: Union[Status, list[str]]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg[0], details=arg[1])

    def max_tasks_required(self) -> int:
        return max([case.processors for case in self.cases])

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    @property
    def stage(self):
        from ..queues import BatchResourceQueue

        return os.path.join(self.root, ".nvtest", BatchResourceQueue.store, str(self.world_id))

    def submission_script_filename(self) -> str:
        basename = f"submit.{self.world_size}.{self.world_rank}.sh"
        return os.path.join(self.stage, basename)

    def logfile(self) -> str:
        basename = f"out.{self.world_size}.{self.world_rank}.txt"
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
        return f"STARTING: Batch {self.world_rank} of {self.world_size} ({n} tests)"

    def end_msg(self) -> str:
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        fmt = "@%s{%d %s}"
        colors = Status.colors
        st_stat = ", ".join(colorize(fmt % (colors[n], v, n)) for (n, v) in stat.items())
        return f"FINISHED: Batch {self.world_rank} of {self.world_size}, {st_stat}"

    def run(self, *args: str, **kwargs: Any) -> None:
        try:
            self._run(*args, **kwargs)
        finally:
            self.refresh()
        return


class SubShell(Batch):
    """Run the Batch in a subshell"""

    def _run(self, *args: str, **kwargs: Any) -> None:
        script = self.write_submission_script(*args, **kwargs)
        if not os.path.exists(script):
            raise ValueError("submission script not found, did you call setup()?")
        script_x = Executable(self.command)
        f = os.path.splitext(script.replace("/submit.", "/out."))[0] + ".txt"
        with open(f, "w") as fh:
            script_x(script, fail_on_error=False, output=fh, error=fh)
        return None

    def write_submission_script(self, *args: str, **kwargs: Any) -> str:
        max_test_cpus = self.max_tasks_required()
        session_cpus = max_test_cpus
        dbg_flag = "-d" if config.get("config:debug") else ""
        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")

        cores_per_socket = config.get("machine:cores_per_socket")
        sockets_per_node = config.get("machine:sockets_per_node") or 1
        cores_per_node = cores_per_socket * sockets_per_node
        qtime = self.cputime / cores_per_node * 1.05

        fh.write(f"# approximate runtime: {hhmmss(qtime)}\n")
        fh.write(f"# batch {self.world_rank} of {self.world_size}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        fh.write("export NVTEST_DISABLE_KB=1\n")
        workers = kwargs.get("workers", 1)
        timeoutx = kwargs.get("timeoutx", 1.0)
        fh.write(
            f"(\n  nvtest {dbg_flag} -C {self.root} run -rv "
            f"-l session:workers:{workers} "
            f"-l session:cpus:{session_cpus} "
            f"-l test:cpus:{max_test_cpus} "
            f"-l test:timeoutx:{timeoutx} "
            f"^{self.world_id}:{self.world_rank}\n)\n"
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
        world_rank: int,
        world_size: int,
        world_id: int = 1,
    ) -> None:
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("slurm runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(cases, world_rank, world_size, world_id=world_id)

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
            logging.error(f"Failed to find jobid for batch {self.world_rank}/{self.world_size}")
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
        try:
            while True:
                state = self.poll(jobid)
                if state is None:
                    return
                time.sleep(0.5)
        except BaseException as e:
            logging.warning(f"cancelling sbatch job {jobid}")
            self.cancel(jobid)
            if isinstance(e, KeyboardInterrupt):
                return
            raise

    def qtime(self, max_tasks: int, nodes: int, timeoutx: float = 1.0) -> float:
        qtime = max(self.cputime / nodes * 1.05, 5)
        if qtime < 100.0:
            qtime = 300.0
        elif qtime < 300.0:
            qtime = 600.0
        elif qtime < 600.0:
            qtime = 1200.0
        elif qtime < 1800.0:
            qtime = 2400.0
        elif qtime < 3600.0:
            qtime = 5000.0
        else:
            qtime *= 1.5
        return qtime * timeoutx

    def write_submission_script(self, *args_in: str, **kwargs: Any) -> str:
        max_tasks = self.max_tasks_required()
        ns = calculate_allocations(max_tasks)
        timeoutx = kwargs.get("timeoutx", 1.0)
        qtime = self.qtime(max_tasks, ns.cores_per_node * ns.nodes, timeoutx=timeoutx)
        args = list(args_in)
        args.append(f"--nodes={ns.nodes}")
        args.append(f"--ntasks-per-node={ns.tasks_per_node}")
        args.append(f"--cpus-per-task={ns.cpus_per_task}")
        args.append(f"--time={hhmmss(qtime, threshold=0)}")
        file = self.logfile()
        args.append(f"--error={file}")
        args.append(f"--output={file}")

        session_cpus = ns.nodes * ns.cores_per_node
        dbg_flag = "-d" if config.get("config:debug") else ""
        fh = StringIO()
        fh.write(f"#!{self.shell}\n")
        for arg in args:
            fh.write(f"#SBATCH {arg}\n")
        fh.write(f"# user: {getuser()}\n")
        fh.write(f"# date: {datetime.now().strftime('%c')}\n")
        fh.write(f"# batch {self.world_rank} of {self.world_size}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        fh.write("export NVTEST_DISABLE_KB=1\n")
        workers = kwargs.get("workers", ns.cores_per_node)
        fh.write(
            f"(\n  nvtest {dbg_flag} -C {self.root} run -rv "
            f"-l session:workers:{workers} "
            f"-l session:cpus:{session_cpus} "
            f"-l test:cpus:{max_tasks} "
            f"-l test:timeoutx:{timeoutx} "
            f"^{self.world_id}:{self.world_rank}\n)\n"
        )
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


# class PBS(Batch):
#    def write_preamble(self, script):
#        """Write the pbs submission script preamble"""
#        if self.auto_allocate:
#            self.calculate_resource_allocations()
#        if "nodes" in self.options and "ppn" in self.options:
#            nodes, ppn = self.options["nodes"], self.options["ppn"]
#            script.write(f"#PBS -l nodes={nodes}:ppn={ppn}\n")
#        elif "nodes" in self.options and "ntasks" in self.options:
#            nodes, ntasks = self.options["nodes"], self.options["ntasks"]
#            if ntasks % nodes != 0:
#                raise ValueError("Unable to equally distribute tasks across nodes")
#            ppn = int(ntasks / nodes)
#            script.write(f"#PBS -l nodes={nodes}:ppn={ppn}\n")
#        else:
#            raise ValueError("Provide nodes and ppn before continuing")
#        for name, value in self.options.items():
#            if value in (False, None) or name in self.resource_attrs:
#                continue
#            prefix = "-" if len(name) == 1 else "--"
#            if name in self.el_opts:
#                option_line = f"#PBS -l {name}={value}\n"
#            elif value is True:
#                option_line = f"#PBS {prefix}{name}\n"
#            else:
#                op = " " if len(name) == 1 else "="
#                option_line = f"#PBS {prefix}{name}{op}{value}\n"
#            script.write(option_line)


def factory(
    cases: Union[list[TestCase], set[TestCase]],
    world_rank: int,
    world_size: int,
    world_id: int = 1,
    scheduler: Optional[str] = None,
) -> Batch:
    batch: Batch
    if scheduler in (None, "shell", "subshell"):
        batch = SubShell(cases, world_rank, world_size, world_id)
    elif scheduler and scheduler.lower() == "slurm":
        batch = Slurm(cases, world_rank, world_size, world_id)
    else:
        raise ValueError(f"{scheduler}: Unknown batch scheduler")
    batch.setup()
    return batch
