import argparse
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from .. import config
from ..test.partition import Partition
from ..util import tty
from ..util.resources import compute_resource_allocations
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
        super().__init__(session, *args)
        parser = self.make_argument_parser()
        self.namespace = argparse.Namespace(wait=True)  # always block
        self.namespace, unknown_args = parser.parse_known_args(
            self.options, namespace=self.namespace
        )
        if unknown_args:
            s_unknown = " ".join(unknown_args)
            tty.die(f"unrecognized slurm arguments: {s_unknown}")

    def calculate_resource_allocations(self, batch: Partition):
        """Performs basic resource calculations"""
        tasks = self.max_tasks_required(batch)
        resources = compute_resource_allocations(
            sockets_per_node=config.get("machine:sockets_per_node"),
            cores_per_socket=config.get("machine:cores_per_socket"),
            ranks=tasks,
        )
        tasks = resources.ranks
        nodes = resources.nodes
        self.namespace.nodes = nodes
        self.namespace.ntasks_per_node = int(tasks / nodes)
        self.namespace.cpus_per_task = 1

    @staticmethod
    def fmt_option_string(key: str) -> str:
        n = 1 if len(key) == 1 else 2
        return f"{'-' * n}{key.replace('_', '-')}"

    def write_header(self, fh: TextIO) -> None:
        """Generate the sbatch script for the current state of arguments."""
        fh.write(f"#!{self.shell}\n")
        if self.namespace.dont_wait:
            self.namespace.wait = False
        for key, value in vars(self.namespace).items():
            if isinstance(value, bool):
                if value is True:
                    fh.write(f"#SBATCH {self.fmt_option_string(key):<19}\n")
            elif value is not None:
                fh.write(f"#SBATCH {self.fmt_option_string(key):<19} {value}\n")

    def __call__(self, batch: Partition, *args: Any) -> dict[str, dict]:
        self.calculate_resource_allocations(batch)
        return super().__call__(batch, *args)
