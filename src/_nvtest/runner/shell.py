from typing import TextIO

from .batch import BatchRunner


class ShellRunner(BatchRunner):
    name = "shell"
    command = "bash"

    def write_header(self, fh: TextIO, batch_no: int) -> None:
        fh.write(f"#!{self.shell}\n")
