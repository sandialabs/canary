import argparse
from typing import TYPE_CHECKING

import nvtest

from .nvtest_run_tests import RunTests

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session


@nvtest.plugin.command(family="info")
class Info(RunTests):
    name = "info"
    description = "Print information about a test run"

    def __init__(self, config: "Config", session: "Session") -> None:
        self.config = config
        self.session = session

    @staticmethod
    def add_options(parser: argparse.ArgumentParser):
        parser.add_argument("dir", help="Test result directory")

    @property
    def mode(self):
        return "read"

    def setup(self):
        self.load_index()

    def run(self) -> int:
        self.print_section_header("Test summary")
        self.print_front_matter()
        args = self.session.orig_invocation_params.args
        self.print_text(f"command: nvtest {' '.join(args)}")
        self.print_test_results_summary()
        return 0

    def teardown(self):
        ...
