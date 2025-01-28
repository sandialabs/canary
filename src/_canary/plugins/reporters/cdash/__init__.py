from ...hookspec import hookimpl
from ...types import CanaryReporterSubcommand
from .reporter import cdash_reporter
from .reporter import setup_parser


@hookimpl
def canary_reporter_subcommand() -> CanaryReporterSubcommand:
    return CanaryReporterSubcommand(
        name="cdash",
        description="CDash reporter",
        setup_parser=setup_parser,
        execute=cdash_reporter,
    )
