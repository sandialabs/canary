# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import os
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from ... import config
from ...hookspec import hookimpl
from ...util import json_helper as json
from ...util import logging
from ...util.filesystem import mkdirp
from ...util.serialize import serialize
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...job import Job
    from ...view import ViewManifestEntry
    from ...view import ViewReportRequest
    from ...workspace import Workspace

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


@hookimpl
def canary_view_report(request: "ViewReportRequest") -> None:
    """Create a JSON report for a completed view snapshot."""
    if "json" not in request.formats:
        return

    reporter = JsonReporter()
    jobs = reporter.load_view_jobs(request)

    output_root = request.output_dir or request.view.metadata_dir / "reports"
    json_request = JsonReportRequest(
        workspace=request.workspace,
        jobs=jobs,
        output=output_root / JsonReporter.default_output,
    )

    reporter.write(json_request)


class JsonReportCommand(CanaryReporter):
    type = "json"
    description = "JSON reporter"

    def setup_parser(self, parser: "Parser") -> None:
        self.add_create_options(parser)

        # Hidden compatibility spelling:
        #
        #   canary report json create
        #
        subparsers = parser.add_subparsers(dest="_json_action", metavar="subcommands")
        p = subparsers.add_parser("create", help=argparse.SUPPRESS)
        self.add_create_options(p)

    def add_create_options(self, parser: "Parser") -> None:
        parser.add_argument(
            "-o",
            "--output",
            default=JsonReporter.default_output,
            help="Output file [default: %(default)s]",
        )

    def run_from_args(self, args: Namespace) -> int:
        from ...workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()

        request = JsonReportRequest(
            workspace=workspace,
            jobs=jobs,
            output=Path(args.output).absolute(),
        )

        JsonReporter().write(request)
        return 0


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

    def load_view_jobs(self, request: "ViewReportRequest") -> list["Job"]:
        """Load jobs represented by the current view manifest.

        The manifest is treated as authoritative for the view snapshot.
        """
        manifest = request.view.load_manifest()
        jobs: list["Job"] = []

        for entry in manifest.entries.values():
            job = self.load_job_from_entry(entry)
            if job is not None:
                jobs.append(job)

        return jobs

    def load_job_from_entry(self, entry: "ViewManifestEntry") -> "Job | None":
        lockfile = Path(entry.source) / "testcase.lock"
        if not lockfile.exists():
            logger.warning(f"{lockfile}: testcase lock not found; skipping report entry")
            return None
        try:
            return json.loads(lockfile.read_text())
        except Exception:
            logger.exception(f"{lockfile}: failed to load testcase lock")
            return None
