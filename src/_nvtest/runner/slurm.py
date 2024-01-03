import argparse
import math
import os
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from .. import config
from ..test.partition import Partition
from ..util.misc import digits
from ..util.time import hhmmss
from ._slurm import _Slurm
from .batch import BatchRunner

if TYPE_CHECKING:
    from ..session import Session


class SlurmRunner(BatchRunner, _Slurm):
    """Setup and submit jobs to the slurm scheduler"""

    name = "slurm"
    shell = "/bin/sh"
    command = "sbatch"

    def __init__(self, session: "Session", *args: Any):
        sockets_per_node = config.get("machine:sockets_per_node")
        cores_per_socket = config.get("machine:cores_per_socket")
        if sockets_per_node is None or cores_per_socket is None:
            raise ValueError(
                "slurm runner requires that both the 'machine:sockets_per_node' "
                "and 'machine:cores_per_socket' be defined"
            )
        super().__init__(session, *args)
        parser = self.make_argument_parser()
        self.namespace = argparse.Namespace(wait=True)  # always block
        self.namespace, unknown_args = parser.parse_known_args(
            self.options, namespace=self.namespace
        )
        if unknown_args:
            s_unknown = " ".join(unknown_args)
            raise ValueError(f"unrecognized slurm arguments: {s_unknown}")

    def calculate_resource_allocations(self, batch: Partition) -> None:
        """Performs basic resource calculations"""
        max_tasks = self.max_tasks_required(batch)
        sockets_per_node = config.get("machine:sockets_per_node")
        cores_per_socket = config.get("machine:cores_per_socket")
        cores_per_node = sockets_per_node * cores_per_socket
        if max_tasks < cores_per_node:
            nodes = 1
            ntasks_per_node = cores_per_node
        else:
            ntasks_per_node = min(max_tasks, cores_per_node)
            nodes = int(math.ceil(max_tasks / cores_per_node))
        self.namespace.nodes = nodes
        self.namespace.ntasks_per_node = ntasks_per_node
        self.namespace.cpus_per_task = 1
        qtime = sum([case.runtime for case in batch])
        self.namespace.time = hhmmss(qtime)

    @staticmethod
    def fmt_option_string(key: str) -> str:
        dashes = "-" if len(key) == 1 else "--"
        return f"{dashes}{key.replace('_', '-')}"

    def write_header(self, fh: TextIO, batch_no: int) -> None:
        """Generate the sbatch script for the current state of arguments."""
        n = max(digits(batch_no), 3)
        basename = f"batch-{batch_no:0{n}}-slurm-out.txt"
        file = os.path.join(self.stage, basename)
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
