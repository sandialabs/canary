import argparse
import os
import subprocess
import time
from datetime import datetime
from io import StringIO
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
        workers: Optional[int] = None,
    ) -> None:
        self.cases = cases
        self.world_rank = world_rank
        self.world_size = world_size
        self.world_id = world_id
        self.use_num_workers = workers
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

    def write_submission_script(self) -> None: ...

    def setup(self, *args: str) -> None:
        self.write_submission_script()
        for case in self.cases:
            if any(dep not in self.cases for dep in case.dependencies):
                self._status.set("pending")
                break
        else:
            self._status.set("ready")

    def _run(self) -> None:
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

    def run(self, *args: str, timeoutx: float = 1.0) -> None:
        script_args = list(args)
        if timeoutx != 1.0:
            script_args.append(f"-l test:timeoutx:{timeoutx}")
        try:
            os.environ["SCRIPT_ARGS"] = " ".join(script_args)
            self._run()
        finally:
            os.environ.pop("SCRIPT_ARGS")
            self.refresh()
        return


class SubShell(Batch):
    """Run the Batch in a subshell"""

    def _run(self) -> None:
        script = self.submission_script_filename()
        if not os.path.exists(script):
            raise ValueError("submission script not found, did you call setup()?")
        script_x = Executable(self.command)
        f = os.path.splitext(script.replace("/submit.", "/out."))[0] + ".txt"
        with open(f, "w") as fh:
            script_x(script, fail_on_error=False, output=fh, error=fh)
        return None

    def write_submission_script(self) -> None:
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
        nodes = 1
        qtime = self.cputime / (cores_per_node * nodes) * 1.05

        fh.write(f"# approximate runtime: {hhmmss(qtime)}\n")
        fh.write(f"# batch {self.world_rank} of {self.world_size}\n")
        fh.write("# test cases:\n")
        for case in self.cases:
            fh.write(f"# - {case.fullname}\n")
        fh.write(f"# total: {len(self.cases)} test cases\n")
        fh.write("export NVTEST_DISABLE_KB=1\n")
        max_workers = self.use_num_workers or 1
        fh.write(
            f"(\n  nvtest {dbg_flag} -C {self.root} run -rv "
            "${SCRIPT_ARGS} "
            f"-l session:workers:{max_workers} "
            f"-l session:cpus:{session_cpus} "
            f"-l test:cpus:{max_test_cpus} "
            f"^{self.world_id}:{self.world_rank}\n)\n"
        )
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return


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
        workers: Optional[int] = None,
    ) -> None:
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("slurm runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(cases, world_rank, world_size, world_id=world_id, workers=workers)

    def setup(self, *args: str) -> None:
        parser = self.make_argument_parser()
        _, unknown_args = parser.parse_known_args(args)
        if unknown_args:
            s_unknown = " ".join(unknown_args)
            raise ValueError(f"unrecognized slurm arguments: {s_unknown}")
        super().setup(*args)

    def _run(self) -> None:
        script = self.submission_script_filename()
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

    def write_submission_script(self, *a: str) -> None:
        max_tasks = self.max_tasks_required()
        ns = calculate_allocations(max_tasks)
        qtime = max(self.cputime / (ns.cores_per_node * ns.nodes) * 1.05, 5)
        if qtime < 300:
            qtime *= 5
        elif qtime < 600:
            qtime *= 3
        elif qtime < 3600:
            qtime *= 1.5
        args = list(a)
        args.append(f"--nodes={ns.nodes}")
        args.append(f"--ntasks-per-node={ns.tasks_per_node}")
        args.append(f"--cpus-per-task={ns.cpus_per_task}")
        args.append(f"--time={hhmmss(qtime, threshold=0)}")
        file = self.logfile()
        args.append(f"--error={file}")
        args.append(f"--output={file}")

        if self.use_num_workers is not None:
            max_workers = self.use_num_workers
        else:
            max_workers = ns.tasks_per_node if ns.nodes == 1 else 1
        max_test_cpus = self.max_tasks_required()
        session_cpus = max(max_workers, max_test_cpus)
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
        fh.write(
            f"(\n  nvtest {dbg_flag} -C {self.root} run -rv "
            "${SCRIPT_ARGS} "
            f"-l session:workers:{max_workers} "
            f"-l session:cpus:{session_cpus} "
            f"-l test:cpus:{max_test_cpus} "
            f"^{self.world_id}:{self.world_rank}\n)\n"
        )
        f = self.submission_script_filename()
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fp:
            fp.write(fh.getvalue())
        set_executable(f)
        return

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

    @staticmethod
    def make_argument_parser():
        parser = argparse.ArgumentParser()
        parser.add_argument("-A", "--account", metavar="<account>")
        parser.add_argument(
            "--acctg_freq", metavar="<datatype><interval>[,<datatype><interval>...]"
        )
        parser.add_argument("-a", "--array", metavar="<indexes>")
        parser.add_argument("--batch", metavar="<list>")
        parser.add_argument("--bb", metavar="<spec>")
        parser.add_argument("--bbf", metavar="<file_name>")
        parser.add_argument("-b", "--begin", metavar="<time>")
        parser.add_argument("-D", "--chdir", metavar="<directory>")
        parser.add_argument("--cluster-constraint", metavar="[!]<list>")
        parser.add_argument("-M", "--clusters", metavar="<string>")
        parser.add_argument("--comment", metavar="<string>")
        parser.add_argument("-C", "--constraint", metavar="<list>")
        parser.add_argument("--container", metavar="<path_to_container>")
        parser.add_argument("--container-id", metavar="<container_id>")
        parser.add_argument("--contiguous", action="store_true", default=False)
        parser.add_argument("-S", "--core-spec", metavar="<num>")
        parser.add_argument("--cores-per-socket", metavar="<cores>")
        parser.add_argument("--cpu-freq", metavar="<p1>[-p2[:p3]]")
        parser.add_argument("--cpus-per-gpu", metavar="<ncpus>")
        parser.add_argument("-c", "--cpus-per-task", metavar="<ncpus>")
        parser.add_argument("--deadline", metavar="<OPT>")
        parser.add_argument("--delay-boot", metavar="<minutes>")
        parser.add_argument("-d", "--dependency", metavar="<dependency_list>")
        parser.add_argument(
            "-m",
            "--distribution",
            metavar="{*|block|cyclic|arbitrary|plane<size>}[:{*|block|cyclic|fcyclic}[:{*|block|cyclic|fcyclic}]][,{Pack|NoPack}]",  # noqa: E501
        )
        parser.add_argument("-e", "--error", metavar="<filename_pattern>")
        parser.add_argument("-x", "--exclude", metavar="<node_name_list>")
        parser.add_argument("--exclusive", metavar="[{user|mcs}]")
        parser.add_argument("--export", metavar="{[ALL,]<environment_variables>|ALL|NONE}")
        parser.add_argument("--export-file", metavar="{<filename>|<fd>}")
        parser.add_argument("--extra", metavar="<string>")
        parser.add_argument("-B", "--extra-node-info", metavar="<sockets>[:cores[:threads]]")
        parser.add_argument("--get-user-env", metavar="[timeout][mode]")
        parser.add_argument("--gid", metavar="<group>")
        parser.add_argument("--gpu-bind", metavar="[verbose,]<type>")
        parser.add_argument("--gpu-freq", metavar="[<type]value>[,<typevalue>][,verbose]")
        parser.add_argument("--gpus-per-node", metavar="[type:]<number>")
        parser.add_argument("--gpus-per-socket", metavar="[type:]<number>")
        parser.add_argument("--gpus-per-task", metavar="[type:]<number>")
        parser.add_argument("-G", "--gpus", metavar="[type:]<number>")
        parser.add_argument("--gres", metavar="<list>")
        parser.add_argument("--gres-flags", metavar="<type>")
        parser.add_argument("--hint", metavar="<type>")
        parser.add_argument("-H", "--hold", action="store_true", default=False)
        parser.add_argument("--ignore-pbs", action="store_true", default=False)
        parser.add_argument("-i", "--input", metavar="<filename_pattern>")
        parser.add_argument("-J", "--job-name", metavar="<jobname>")
        parser.add_argument("--kill-on-invalid-dep", metavar="<yes|no>")
        parser.add_argument(
            "-L",
            "--licenses",
            metavar="<license>[@db][:count][,license[@db][:count]...]",
        )
        parser.add_argument("--mail-type", metavar="<type>")
        parser.add_argument("--mail-user", metavar="<user>")
        parser.add_argument("--mcs-label", metavar="<mcs>")
        parser.add_argument("--mem", metavar="<size>[units]")
        parser.add_argument("--mem-bind", metavar="[{quiet|verbose},]<type>")
        parser.add_argument("--mem-per-cpu", metavar="<size>[units]")
        parser.add_argument("--mem-per-gpu", metavar="<size>[units]")
        parser.add_argument("--mincpus", metavar="<n>")
        parser.add_argument("--network", metavar="<type>")
        parser.add_argument("--nice", metavar="[adjustment]")
        parser.add_argument("-k", "--no-kill", metavar="[off]")
        parser.add_argument("--no_requeue", action="store_true", default=False)
        parser.add_argument("-F", "--nodefile", metavar="<node_file>")
        parser.add_argument("-w", "--nodelist", metavar="<node_name_list>")
        parser.add_argument("-N", "--nodes", metavar="<minnodes>[-maxnodes]|<size_string>")
        parser.add_argument("--ntasks-per-core", metavar="<ntasks>")
        parser.add_argument("--ntasks-per-gpu", metavar="<ntasks>")
        parser.add_argument("--ntasks-per-node", metavar="<ntasks>")
        parser.add_argument("--ntasks-per-socket", metavar="<ntasks>")
        parser.add_argument("-n", "--ntasks", metavar="<number>")
        parser.add_argument("--open_mode", metavar="{append|truncate}")
        parser.add_argument("-o", "--output", metavar="<filename_pattern>")
        parser.add_argument("-O", "--overcommit", action="store_true", default=False)
        parser.add_argument("-s", "--oversubscribe", action="store_true", default=False)
        parser.add_argument("-p", "--partition", metavar="<partition_names>")
        parser.add_argument("--power", metavar="<flags>")
        parser.add_argument("--prefer", metavar="<list>")
        parser.add_argument("--priority", metavar="<value>")
        parser.add_argument("--profile", metavar="{all|none|<type>[,<type>...]}")
        parser.add_argument("--propagate", metavar="[rlimit[,rlimit...]]")
        parser.add_argument("-q", "--qos", metavar="<qos>")
        parser.add_argument("-Q", "--quiet", action="store_true", default=False)
        parser.add_argument("--reboot", action="store_true", default=False)
        parser.add_argument("--requeue", action="store_true", default=False)
        parser.add_argument("--reservation", metavar="<reservation_names>")
        parser.add_argument("--signal", metavar="[{R|B}:]<sig_num>[@sig_time]")
        parser.add_argument("--sockets-per-node", metavar="<sockets>")
        parser.add_argument("--spread-job", action="store_true", default=False)
        parser.add_argument("--switches", metavar="<count>[@max-time]")
        parser.add_argument("--test-only", action="store_true", default=False)
        parser.add_argument("--thread-spec", metavar="<num>")
        parser.add_argument("--threads-per-core", metavar="<threads>")
        parser.add_argument("--time-min", metavar="<time>")
        parser.add_argument("-t", "--time", metavar="<time>")
        parser.add_argument("--tmp", metavar="<size>[units]")
        parser.add_argument("--tres-per-task", metavar="<list>")
        parser.add_argument("--uid", metavar="<user>")
        parser.add_argument("--use-min-nodes", action="store_true", default=False)
        parser.add_argument("-v", "--verbose", metavar="<value>")
        # parser.add_argument("--wait-all-nodes", metavar="<value>")
        # g.add_argument("-W", "--wait", action="store_true", default=False)
        parser.add_argument("--wckey", metavar="<wckey>")
        parser.add_argument("--wrap", metavar="<command_string>")
        return parser


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
    avail_workers: Optional[int] = None,
) -> Batch:
    if scheduler in (None, "shell", "subshell"):
        return SubShell(cases, world_rank, world_size, world_id, workers=avail_workers)
    assert scheduler is not None
    if scheduler.lower() == "slurm":
        return Slurm(cases, world_rank, world_size, world_id, workers=avail_workers)
    raise ValueError(f"{scheduler}: Unknown batch scheduler")
