import argparse
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

from ..runner import valid_runners
from ..util.time import time_in_seconds
from ..util.tty.color import colorize
from .common import add_mark_arguments
from .common import add_timing_arguments
from .common import add_workdir_arguments
from .run_tests import RunTests

if TYPE_CHECKING:
    from ..config.argparsing import Parser


class RunnerOptions(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: Union[str, Sequence[Any], None],
        option_str: Optional[str] = None,
    ):
        runner_opts: list[str] = getattr(namespace, self.dest, None) or []
        assert isinstance(option, str)
        options: list[str] = option.replace(",", " ").split()
        runner_opts.extend(options)
        setattr(namespace, self.dest, runner_opts)


class RunBatched(RunTests):
    """Run the tests in batches through a scheduler"""

    family = "batch"

    @staticmethod
    def setup_parser(parser: "Parser"):
        add_workdir_arguments(parser)
        add_mark_arguments(parser)
        add_timing_arguments(parser)
        parser.add_argument(
            "--concurrent-batches",
            dest="max_workers",
            type=int,
            default=5,
            help="Number of concurrent batches to run [default: %(default)s]",
        )
        parser.add_argument(
            "--batch-size",
            type=time_in_seconds,
            default=30 * 60,
            help="Batch size in seconds [default: 30m]",
        )
        parser.add_argument(
            "--copy-all-resources",
            action="store_true",
            help="Do not link resources to the test "
            "directory, only copy [default: %(default)s]",
        )
        parser.add_argument(
            "--runner",
            default="none",
            choices=valid_runners,
            help="Work load manager [default: %(default)s]",
        )
        help_msg = colorize(
            "Pass @*{option} as an option to the runner. "
            "If @*{option} contains commas, it is split into multiple options at the "
            "commas. You can use this syntax to pass an argument to the option. "
            "For example, -R,-A,XXXX passes -A XXXX to the runner."
        )
        parser.add_argument(
            "-R",
            action=RunnerOptions,
            dest="runner_options",
            metavar="option",
            help=help_msg,
        )
        parser.add_argument("search_paths", nargs="+", help="Search paths")
