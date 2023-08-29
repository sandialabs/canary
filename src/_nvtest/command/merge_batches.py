import glob
import json
import os
from typing import TYPE_CHECKING

from _nvtest.test.partition import merge
from _nvtest.util import tty

from .common import Command

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session


class MergeBatches(Command):
    name = "merge-batches"
    description = "Merge batched test results"

    def __init__(self, config: "Config", session: "Session") -> None:
        super().__init__(config, session)
        files = self.session.option.files
        if len(files) == 1 and self.session.is_workdir(files[0]):
            if self.session.option.workdir is not None:
                raise ValueError("Do not set value of work-dir when merging tests")
            self.session.option.workdir = files[0]
            files = glob.glob(
                os.path.join(self.session.option.workdir, ".nvtest", "testcases.json.*")
            )
            if not self.session.option.o:
                dir = os.path.dirname(files[0])
                self.session.option.o = os.path.join(dir, "testcases.json")
            if not files:
                tty.die(f"No files found in {self.session.option.workdir}")
        self.files: list[str] = files

    @property
    def mode(self):
        return "append"

    def run(self) -> int:
        merged = merge(self.files)
        output_file = self.session.option.o or "merged.json"
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
