import argparse
import math
import os
import subprocess
import time
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import TextIO

from .. import config
from ..test.partition import Partition
from ..util import logging
from ..util.executable import Executable
from ..util.time import hhmmss
from .batch import BatchRunner

if TYPE_CHECKING:
    from ..session import Session


class SlurmRunner(BatchRunner):
    """Setup and submit jobs to the slurm scheduler"""

    name = "slurm"
    shell = "/bin/sh"
    command = "sbatch"

    def __init__(self, session: "Session", **kwargs: Any):
        cores_per_socket = config.get("machine:cores_per_socket")
        if cores_per_socket is None:
            raise ValueError("slurm runner requires that 'machine:cores_per_socket' be defined")
        super().__init__(session, **kwargs)
        parser = self.make_argument_parser()
        self.namespace = argparse.Namespace()
        self.namespace, unknown_args = parser.parse_known_args(
            self.options, namespace=self.namespace
        )
        if unknown_args:
            s_unknown = " ".join(unknown_args)
            raise ValueError(f"unrecognized slurm arguments: {s_unknown}")

    def calculate_resource_allocations(self, batch: Partition) -> None:
        """Performs basic resource calculations"""
        max_tasks = self.max_tasks_required(batch)
        cores_per_socket = config.get("machine:cores_per_socket")
        sockets_per_node = config.get("machine:sockets_per_node") or 1
        cores_per_node = cores_per_socket * sockets_per_node
        if max_tasks < cores_per_node:
            nodes = 1
            ntasks_per_node = cores_per_node
        else:
            ntasks_per_node = min(max_tasks, cores_per_node)
            nodes = int(math.ceil(max_tasks / cores_per_node))
        self.namespace.nodes = nodes
        self.namespace.ntasks_per_node = ntasks_per_node
        self.namespace.cpus_per_task = 1
        qtime = batch.cputime / (cores_per_node * nodes) * 1.05
        self.namespace.time = hhmmss(qtime)

    @staticmethod
    def fmt_option_string(key: str) -> str:
        dashes = "-" if len(key) == 1 else "--"
        return f"{dashes}{key.replace('_', '-')}"

    def write_header(self, fh: TextIO, batch: Partition) -> None:
        """Generate the sbatch script for the current state of arguments."""
        self.calculate_resource_allocations(batch)
        file = self.logfile(batch)
        self.namespace.error = self.namespace.output = file
        fh.write(f"#!{self.shell}\n")
        for key, value in vars(self.namespace).items():
            if isinstance(value, bool):
                if value is True:
                    fh.write(f"#SBATCH {self.fmt_option_string(key):<19}\n")
            elif value is not None:
                fh.write(f"#SBATCH {self.fmt_option_string(key):<19} {value}\n")

    def avail_workers(self, batch):
        if self.namespace.nodes == 1:
            return self.namespace.ntasks_per_node
        return 1

    def _run(self, batch: Partition) -> None:
        script = self.submit_filename(batch)
        if not os.path.exists(script):
            self.write_submission_script(batch)
        args = [self.command]
        if self.default_args:
            args.extend(self.default_args)
        args.append(script)
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = p.communicate()
        result = str(out.decode("utf-8")).strip()
        i = result.find("Submitted batch job")
        if i >= 0:
            parts = result[i:].split()
            if len(parts) > 3 and parts[3]:
                jobid = parts[3]
        else:
            logging.error(f"Failed to find jobid for batch {batch.world_id}:{batch.world_rank}")
            logging.error(out)
            return
        logging.debug(f"Submitted batch with jobid={jobid}")

        time.sleep(1)
        try:
            while True:
                state = self.query(jobid)
                if state is None:
                    return
                time.sleep(0.5)
        except BaseException as e:
            logging.warning(f"cancelling sbatch job {jobid}")
            self.cancel(jobid)
            if isinstance(e, KeyboardInterrupt):
                return
            raise

    def query(self, jobid: str) -> Optional[str]:
        squeue = Executable("squeue")
        out = squeue("--noheader", "-o", "%i %t", "--clusters=all", output=str)
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
