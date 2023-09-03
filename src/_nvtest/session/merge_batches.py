import glob
import json
import os
from typing import Optional

from ..test.partition import merge
from ..util import tty
from .base import Session


class MergeBatches(Session):
    """Merge batched test results"""

    family = "batch"

    def __init__(
        self, *, invocation_params: Optional[Session.InvocationParams] = None
    ) -> None:
        super().__init__(invocation_params=invocation_params)
        files = self.option.files
        if len(files) == 1 and self.is_workdir(files[0]):
            if self.option.workdir is not None:
                raise ValueError("Do not set value of work-dir when merging tests")
            self.option.workdir = files[0]
            files = glob.glob(
                os.path.join(self.option.workdir, ".nvtest", "testcases.json.*")
            )
            if not self.option.o:
                dir = os.path.dirname(files[0])
                self.option.o = os.path.join(dir, "testcases.json")
            if not files:
                tty.die(f"No files found in {self.option.workdir}")
        self.files: list[str] = files

    @property
    def mode(self):
        return self.Mode.APPEND

    def run(self) -> int:
        merged = merge(self.files)
        output_file = self.option.o or "merged.json"
        with open(output_file, "w") as fh:
            cases = []
            for case in merged:
                cases.append(case.asdict())
            json.dump(cases, fh, indent=2)
        return 0

    @staticmethod
    def add_options(parser):
        parser.add_argument(
            "-o", default=None, help="Output file name [default: merged.json]"
        )
        parser.add_argument("files", nargs="+", help="Partitioned test file")
