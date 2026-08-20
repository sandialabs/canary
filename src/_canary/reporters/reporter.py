import os
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
        help="Write final report in this format [default: none]",
    )


@hookimpl
def canary_cmdline_modifyargs(parser: "Parser", args: Namespace) -> None:
    if report_formats := getattr(args, "report", None):
        if "none" in report_formats:
            report_formats = ["none"]
        args.report = report_formats


def enabled(report_type: str) -> bool:
    from .. import config

    if os.getenv("CANARY_LEVEL", "0") != "0":
        return False
    reports = config.getoption("report")
    if reports is not None:
        return bool(reports) and "none" not in reports and report_type in reports
    return False
    # return not running_in_ci() and report_type == "html"


def running_in_ci() -> bool:
    return any(os.getenv(name) for name in ("GITHUB_ACTIONS", "GITLAB_CI", "CI"))


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
