from typing import TextIO

from ..test.partition import Partition
from .batch import BatchRunner


class ShellRunner(BatchRunner):
    name = "shell"
    command = "bash"

    def write_header(self, fh: TextIO, batch: Partition) -> None:
        fh.write(f"#!{self.shell}\n")
