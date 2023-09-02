import os
from typing import Optional

from .argparsing import ArgumentParser
from .base import Session

class Info(Session):
    """Print information about a test run"""

    def __init__(self, *, invocation_params: Optional[Session.InvocationParams] = None) -> None:
        super().__init__(invocation_params=invocation_params)
        dir = self.option.directory
        if not self.is_workdir(dir):
            raise ValueError(f"{dir!r} is not a test execution directory")
        self.option.workdir = dir

    @staticmethod
    def setup_parser(parser: ArgumentParser):
        parser.add_argument("directory", help="Test result directory")

    @property
    def mode(self):
        return self.Mode.READ

    def run(self) -> int:
        self.load_index()
        self.print_section_header("Test summary")
        self.print_front_matter()
        args = self.orig_invocation_params.args
        self.print_text(f"command: nvtest {' '.join(args)}")
        self.print_test_results_summary()
        return 0

    def teardown(self):
        ...
