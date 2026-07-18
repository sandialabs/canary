from argparse import Namespace
from typing import TYPE_CHECKING

from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--report",
        default=None,
        action="append",
        command=("run",),
        choices={"html", "markdown", "junit", "json", "none"},
        help="Write final report in this format [default: html]",
    )


@hookimpl
def canary_cmdline_modifyargs(parser: "Parser", args: Namespace) -> None:
    if hasattr(args, "report"):
        report_formats = args.report or ["html"]
        if "none" in report_formats:
            report_formats = ["none"]
        args.report = report_formats


def enabled(report_type: str) -> bool:
    from .. import config

    reports = config.getoption("report") or ["html"]
    return "none" not in reports and report_type in reports


class CanaryReporter:
    """Canary report command descriptor.

    Simple reporters should implement:

        canary report <type>

    Complex reporters, such as CDash, may override setup_parser and
    run_from_args to provide their own subcommands.
    """

    type: str
    description: str

    def setup_parser(self, parser: "Parser") -> None:
        pass

    def run_from_args(self, args: Namespace) -> int:
        raise NotImplementedError
