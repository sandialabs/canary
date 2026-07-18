# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import os
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from .. import config
from ..hookspec import hookimpl
from ..util import json_helper as json
from ..util import logging
from ..util.filesystem import mkdirp
from ..util.serialize import serialize
from .reporter import CanaryReporter
from .reporter import enabled

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..job import Job
    from ..runtest import Runner
    from ..workspace import Workspace

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class JsonReportRequest:
    """Inputs required to render a JSON report.

    This request is intentionally not tied to a view. View lifecycle reporting
    and the standalone `canary report json` command both adapt their context
    into this renderer request.
    """

    workspace: "Workspace"
    jobs: list["Job"]
    output: Path


@hookimpl
def canary_reporter() -> CanaryReporter:
    return JsonReportCommand()


@hookimpl(trylast=True)
def canary_runtests_report(runner: "Runner") -> None:
    """Create a JSON report for a completed jobs."""
    if not enabled("json"):
        return
    reporter = JsonReporter()
    ws = runner.workspace
    json_request = JsonReportRequest(
        workspace=ws, jobs=runner.jobs, output=ws.reports_dir / JsonReporter.default_output
    )
    reporter.write(json_request)


class JsonReportCommand(CanaryReporter):
    type = "json"
    description = "JSON reporter"

    def setup_parser(self, parser: "Parser") -> None:
        # Compatibility positional:
        #
        #   canary report json create
        #
        # The preferred spelling is:
        #
        #   canary report json
        #
        parser.add_argument(
            "_create", nargs="?", choices=("create",), metavar="", help=argparse.SUPPRESS
        )
        parser.add_argument(
            "-o",
            "--output",
            default=JsonReporter.default_output,
            help="Output file [default: %(default)s]",
        )
        parser.set_defaults(_json_report_handler=self.run_create)

    def run_from_args(self, args: Namespace) -> int:
        handler = getattr(args, "_json_report_handler", None)
        if handler is None:
            raise ValueError("canary report json: missing action")
        handler(args)
        return 0

    def run_create(self, args: Namespace) -> None:
        from ..workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        output = Path(args.output).absolute()
        request = JsonReportRequest(workspace=workspace, jobs=jobs, output=output)
        JsonReporter().write(request)


class JsonReporter:
    """JSON renderer for Canary reports."""

    type = "json"
    description = "JSON reporter"
    default_output = "canary.json"

    def write(self, request: JsonReportRequest) -> Path:
        """Write a JSON report and return the output path."""
        output = request.output
        mkdirp(output.parent)

        tmp = output.with_name(f".{output.name}.tmp-{os.getpid()}")

        data: dict[str, object] = {}
        for job in request.jobs:
            data[job.id] = serialize(job)

        try:
            with open(tmp, "w") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, output)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        rel = os.path.relpath(output, config.invocation_dir)
        logger.info(f"JSON report written to {rel}")
        return output
