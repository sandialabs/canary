import shlex
from typing import TYPE_CHECKING

from .base import Session

if TYPE_CHECKING:
    from ..config import Config
    from ..config.argparsing import Parser


class Info(Session):
    """Print information about a test run"""

    family = "info"

    def __init__(self, *, config: "Config") -> None:
        super().__init__(config=config)
        dir = self.option.directory
        if not self.is_workdir(dir):
            raise ValueError(f"{dir!r} is not a test execution directory")
        self.workdir = dir

    @staticmethod
    def setup_parser(parser: "Parser"):
        parser.add_argument("directory", help="Test result directory")

    @property
    def mode(self):
        return self.Mode.READ

    def setup(self) -> None:
        self.cases = self.load_index()

    def run(self) -> int:
        self.print_section_header("Test summary")
        self.print_front_matter()
        args = self.config.orig_invocation_params.args
        self.print_text(f"command: nvtest {shlex.join(args)}")
        self.print_test_results_summary()
        return 0

    def teardown(self):
        ...
