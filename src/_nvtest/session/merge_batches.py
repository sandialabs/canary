import glob
import json
import os
from typing import Optional

from ..test.partition import merge
from ..util.filesystem import mkdirp
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
            self.workdir = files[0]
            files = glob.glob(
                os.path.join(self.workdir, ".nvtest", "testcases.json.*")
            )
            if not files:
                tty.die(f"No files found in {self.workdir}")
        else:
            self.workdir = self.find_workdir(files[0])
        self.files: list[str] = files

    @property
    def mode(self):
        return self.Mode.APPEND

    @staticmethod
    def find_workdir(start: str) -> str:
        path = start
        while True:
            f = os.path.join(path, ".nvtest/session.json")
            if os.path.exists(f):
                return path
            path = os.path.dirname(path)
            if path == "/":
                raise ValueError("Could not find workdir")

    def run(self) -> int:
        merged = merge(self.files)
        mkdirp(self.option.o)
        with open(self.option.o, "w") as fh:
            cases = []
            for case in merged:
                cases.append(case.asdict())
            json.dump(cases, fh, indent=2)
        return 0

    @staticmethod
    def add_options(parser):
        parser.add_argument(
            "-o", default="merged.json", help="Output file name [default: %(default)s]"
        )
        parser.add_argument("files", nargs="+", help="Partitioned test files")
