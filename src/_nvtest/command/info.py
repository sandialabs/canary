import os
from typing import TYPE_CHECKING

from ..session.argparsing import ArgumentParser
from .common import Command
from .common import ConsolePrinter
from .common import load_index

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session


class Info(Command, ConsolePrinter):
    name = "info"
    description = "Print information about a test run"

    def __init__(self, config: "Config", session: "Session") -> None:
        self.config = config
        self.session = session
        dir = self.session.option.directory
        if not self.session.is_workdir(dir):
            raise ValueError(f"{dir!r} is not a test execution directory")
        self.session.option.workdir = dir

    @staticmethod
    def add_options(parser: ArgumentParser):
        parser.add_argument("directory", help="Test result directory")

    @property
    def mode(self):
        return "read"

    @property
    def log_level(self) -> int:
        return self.config.log_level

    def run(self) -> int:
        file = os.path.join(self.session.dotdir, "index.json")
        self.cases, _ = load_index(file)
        self.print_section_header("Test summary")
        self.print_front_matter()
        args = self.session.orig_invocation_params.args
        self.print_text(f"command: nvtest {' '.join(args)}")
        self.print_test_results_summary()
        return 0

    def teardown(self):
        ...
