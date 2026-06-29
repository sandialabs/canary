# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import os
import re
import xml.dom.minidom as xdom
import xml.sax.saxutils
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from ... import config
from ...hookspec import hookimpl
from ...util import json_helper as json
from ...util import logging
from ...util.filesystem import mkdirp
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...job import Job
    from ...view import ViewManifestEntry
    from ...view import ViewReportRequest
    from ...workspace import Workspace

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class JunitReportRequest:
    """Inputs required to render a JUnit report.

    This request is intentionally not tied to a view. View lifecycle reporting
    and the standalone `canary report junit` command both adapt their context
    into this renderer request.
    """

    workspace: "Workspace"
    jobs: list["Job"]
    output: Path


@hookimpl
def canary_reporter() -> CanaryReporter:
    return JunitReportCommand()


@hookimpl
def canary_view_report(request: "ViewReportRequest") -> None:
    """Create a JUnit XML report for a completed view snapshot."""
    if "junit" not in request.formats:
        return

    reporter = JunitReporter()
    jobs = reporter.load_view_jobs(request)

    output_root = request.output_dir or request.view.metadata_dir / "reports"
    junit_request = JunitReportRequest(
        workspace=request.workspace,
        jobs=jobs,
        output=output_root / JunitReporter.default_output,
    )

    reporter.write(junit_request)


class JunitReportCommand(CanaryReporter):
    type = "junit"
    description = "JUnit reporter"

    def setup_parser(self, parser: "Parser") -> None:
        self.add_create_options(parser)

        # Hidden compatibility spelling:
        #
        #   canary report junit create
        #
        subparsers = parser.add_subparsers(dest="_junit_action", metavar="subcommands")
        p = subparsers.add_parser("create", help=argparse.SUPPRESS)
        self.add_create_options(p)

    def add_create_options(self, parser: "Parser") -> None:
        parser.add_argument(
            "-o",
            "--output",
            default=JunitReporter.default_output,
            help="Output file [default: %(default)s]",
        )

    def run_from_args(self, args: Namespace) -> int:
        from ...workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()

        request = JunitReportRequest(
            workspace=workspace,
            jobs=jobs,
            output=Path(args.output).absolute(),
        )

        JunitReporter().write(request)
        return 0


class JunitReporter:
    """JUnit XML renderer for Canary reports."""

    type = "junit"
    description = "JUnit reporter"
    default_output = "junit.xml"

    def write(self, request: JunitReportRequest) -> Path:
        """Write a JUnit XML report and return the output path."""
        doc = JunitDocument()
        root = doc.create_testsuite_element(
            request.jobs,
            name=get_root_name(),
            tagname="testsuites",
        )

        groups = groupby_classname(request.jobs)
        for classname, jobs in groups.items():
            suite = doc.create_testsuite_element(jobs, name=classname)
            for job in jobs:
                el = doc.create_testcase_element(job)
                suite.appendChild(el)
            root.appendChild(suite)

        doc.appendChild(root)

        output = request.output
        mkdirp(output.parent)
        tmp = output.with_name(f".{output.name}.tmp-{os.getpid()}")

        try:
            with open(tmp, "w") as fh:
                fh.write(doc.toprettyxml(indent="  ", newl="\n"))
            os.replace(tmp, output)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        rel = os.path.relpath(output, config.invocation_dir)
        logger.info(f"JUnit report written to {rel}")
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


def get_root_name() -> str:
    name = "Canary Session"
    if "CI_MERGE_REQUEST_IID" in os.environ:
        name = f"Merge Request {os.environ['CI_MERGE_REQUEST_IID']}"
    elif "CI_JOB_NAME" in os.environ:
        name = os.environ["CI_JOB_NAME"].replace(":", " ")
    return name


def groupby_classname(jobs: list["Job"]) -> dict[str, list["Job"]]:
    grouped: dict[str, list["Job"]] = {}
    for job in jobs:
        classname = get_classname(job)
        grouped.setdefault(classname, []).append(job)
    return grouped


def get_classname(job: "Job") -> str:
    if "classname" in job.spec.attributes:
        return job.spec.attributes["classname"]
    return job.spec.file_path.parent.name


class JunitDocument(xdom.Document):
    def create_element(self, tagname: str) -> xdom.Element:
        element = xdom.Element(tagname)
        element.ownerDocument = self
        return element

    def create_cdata_node(self, text: str) -> xdom.CDATASection:
        node = xdom.CDATASection()
        node.data = cleanup_text(text)
        node.ownerDocument = self
        return node

    def create_testsuite_element(
        self,
        jobs: list["Job"],
        tagname: str = "testsuite",
        **attrs: str,
    ) -> xdom.Element:
        """Create a testsuite/testsuites element."""
        element = self.create_element(tagname)
        stats = gather_statistics(jobs)

        for name, value in attrs.items():
            element.setAttribute(name, value)

        element.setAttribute("tests", str(stats.num_tests))
        element.setAttribute("errors", str(stats.num_error))
        element.setAttribute("skipped", str(stats.num_skipped))
        element.setAttribute("failures", str(stats.num_failed))
        element.setAttribute("time", str(stats.time))
        element.setAttribute("timestamp", stats.timestamp)

        return element

    def create_testcase_element(self, job: "Job") -> xdom.Element:
        testcase = self.create_element("testcase")
        testcase.setAttribute("name", job.display_name())
        testcase.setAttribute("classname", get_classname(job))
        testcase.setAttribute("time", str(job.timekeeper.duration()))
        testcase.setAttribute("file", getattr(job, "relpath", str(job.spec.file_path)))

        if job.status.is_failure():
            failure = self.create_element("failure")
            failure.setAttribute("message", f"Test job status: {job.status.outcome.name}")
            failure.setAttribute("type", job.status.outcome.name)
            testcase.appendChild(failure)

            system_out = self.create_element("system-out")
            system_out.appendChild(self.create_cdata_node(job.read_output()))
            testcase.appendChild(system_out)

            if "CI_SERVER_VERSION_MAJOR" in os.environ:
                # Older versions of GitLab only read from <failure>...</failure>.
                major = int(os.environ["CI_SERVER_VERSION_MAJOR"])
                minor = int(os.environ["CI_SERVER_VERSION_MINOR"])
                if (major, minor) < (16, 5):
                    failure.appendChild(self.create_cdata_node(job.read_output()))

        elif job.status.is_skipped():
            skipped = self.create_element("skipped")
            skipped.setAttribute("message", job.status.outcome.name)
            testcase.appendChild(skipped)

        return testcase


def gather_statistics(jobs: list["Job"]) -> SimpleNamespace:
    stats = SimpleNamespace(num_skipped=0, num_failed=0, num_error=0, num_tests=0, time=0.0)
    started_on: datetime | None = None
    finished_on: datetime | None = None

    for job in jobs:
        stats.num_tests += 1

        if job.status.is_failure():
            stats.num_failed += 1
        elif job.status.is_skipped():
            stats.num_skipped += 1
        elif not job.state.is_done():
            stats.num_error += 1

        if job.state.is_done():
            t = job.timekeeper.started
            if started_on is None:
                if t > 0:
                    started_on = datetime.fromtimestamp(t)
            elif t > 0 and datetime.fromtimestamp(t) < started_on:
                started_on = datetime.fromtimestamp(t)

            t = job.timekeeper.finished
            if finished_on is None:
                if t > 0:
                    finished_on = datetime.fromtimestamp(t)
            elif t > 0 and datetime.fromtimestamp(t) > finished_on:
                finished_on = datetime.fromtimestamp(t)

    stats.started_on = started_on
    stats.finished_on = finished_on

    if started_on is not None and finished_on is not None:
        stats.timestamp = started_on.strftime("%Y-%m-%dT%H:%M:%S")
        stats.time = (finished_on - started_on).total_seconds()
    else:
        stats.timestamp = "NA"

    return stats


def cleanup_text(text: str, escape: bool = False) -> str:
    # First strip ANSI color sequences from string.
    text = re.sub(r"\033[^m]*m", "", text)
    if escape:
        text = xml.sax.saxutils.escape(text)
    return text
