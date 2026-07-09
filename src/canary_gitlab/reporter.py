# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import os
import re
from argparse import Namespace

import canary

from . import gitlab

logger = canary.get_logger(__name__)


class GitLabMRReporter(canary.CanaryReporter):
    type = "gitlab-mr"
    description = "GitLab merge request reporter"

    def setup_parser(self, parser: "canary.Parser") -> None:
        # Compatibility positional:
        #
        #   canary report gitlab-mr create
        #
        # The preferred spelling is:
        #
        #   canary report gitlab-mr
        #
        parser.add_argument(
            "_create", nargs="?", choices=("create",), metavar="", help=argparse.SUPPRESS
        )
        parser.add_argument("--cdash-url", help="Add a link to a CDash report for this MR")
        parser.add_argument(
            "-a",
            "--access-token",
            help="GitLab access token that allows GET/POST to the merge request API",
        )
        parser.set_defaults(_gitlab_mr_handler=self.run_create)

    def run_from_args(self, args: Namespace) -> int:
        handler = getattr(args, "_gitlab_mr_handler", None)
        if handler is None:
            raise ValueError("canary report gitlab-mr: missing action")
        handler(args)
        return 0

    def run_create(self, args: Namespace) -> None:
        workspace = canary.Workspace.load()

        mr = MergeRequest(access_token=args.access_token)
        failed = group_failed_jobs(workspace.load_jobs())

        if failed:
            mr.report_failed(failed, cdash_build_url=args.cdash_url)
        else:
            mr.report_success(cdash_build_url=args.cdash_url)


class MergeRequest:
    def __init__(self, access_token: str | None = None):
        if "GITLAB_CI" not in os.environ:
            raise MissingCIVariable("GITLAB_CI")

        if access_token is None:
            for var in ("GITLAB_ACCESS_TOKEN", "ACCESS_TOKEN"):
                if var in os.environ:
                    access_token = os.environ[var]
                    break
            else:
                raise MissingCIVariable("GITLAB_ACCESS_TOKEN")

        for var in ("CI_MERGE_REQUEST_IID", "CI_PROJECT_ID", "CI_API_V4_URL"):
            if var not in os.environ:
                raise MissingCIVariable(var)

        self.access_token = access_token
        iid = os.environ["CI_MERGE_REQUEST_IID"]
        project_id = os.environ["CI_PROJECT_ID"]
        api_v4_url = os.environ["CI_API_V4_URL"]

        self.backend = gitlab.merge_request(api_v4_url, project_id, iid, self.access_token)
        self.job_name = os.getenv("CI_JOB_NAME", "Unknown")
        self.iid = self.backend.iid
        self.id = self.backend.id
        self.title = self.backend.title

    def add_note(self, note: str) -> None:
        self.backend.add_note(note)

    def report_failed(
        self, failed_cases: dict[str, list["canary.Job"]], cdash_build_url: str | None = None
    ) -> None:
        fp = io.StringIO()
        job = re.sub(":(build|test|report)", "", self.job_name)
        fp.write(f"Merge request pipeline `{escape_markdown(job)}` failed\n\n")

        num_failed = sum(len(jobs) for jobs in failed_cases.values())
        sec = "<h3>Failed test summary</h3>"
        detail_threshold = 5

        if num_failed > detail_threshold:
            fp.write(f"<details>\n<summary>{sec} (click to expand)</summary>\n\n")
        else:
            fp.write(f"{sec}\n\n")

        fp.write("| Test | Status |\n")
        fp.write("| --- | --- |\n")

        for status in sorted(failed_cases):
            for job in sorted(failed_cases[status], key=lambda j: j.display_name()):
                fp.write(
                    f"| {escape_table_cell(job.display_name())} | {escape_table_cell(status)} |\n"
                )

        fp.write("\n")

        if num_failed > detail_threshold:
            fp.write("</details>\n\n")

        if cdash_build_url is not None:
            fp.write(f"See the [CDash entry]({cdash_build_url}) for details.\n\n")

        self.add_note(fp.getvalue())

    def report_success(self, cdash_build_url: str | None = None) -> None:
        fp = io.StringIO()
        job = re.sub(":(build|test|report)", "", self.job_name)
        fp.write(f"Merge request pipeline `{escape_markdown(job)}` finished successfully\n\n")

        if cdash_build_url is not None:
            fp.write(f"See the [CDash entry]({cdash_build_url}) for details.\n\n")

        note = fp.getvalue()
        logger.info(note)
        self.add_note(note)


def group_failed_jobs(jobs: list["canary.Job"]) -> dict[str, list["canary.Job"]]:
    failed: dict[str, list["canary.Job"]] = {}

    for job in jobs:
        if not job.status.is_success():
            failed.setdefault(job.status.outcome.name, []).append(job)

    return failed


def escape_table_cell(value: object) -> str:
    return (
        str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
    )


def escape_markdown(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("\n", " ")


class MissingCIVariable(Exception):
    pass
