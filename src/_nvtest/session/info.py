from typing import Optional

from .argparsing import Parser
from .base import Session


class Info(Session):
    """Print information about a test run"""

    family = "info"

    def __init__(
        self, *, invocation_params: Optional[Session.InvocationParams] = None
    ) -> None:
        super().__init__(invocation_params=invocation_params)
        dir = self.option.directory
        if not self.is_workdir(dir):
            raise ValueError(f"{dir!r} is not a test execution directory")
        self.workdir = dir

    @staticmethod
    def setup_parser(parser: Parser):
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
