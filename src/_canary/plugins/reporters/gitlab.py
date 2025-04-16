# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import os
import re
from typing import TYPE_CHECKING
from typing import Any

from ...test.case import TestCase
from ...util import gitlab
from ...util import logging
from ..hookspec import hookimpl
from ..types import CanaryReport

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...session import Session


@hookimpl
def canary_session_report() -> CanaryReport:
    return GitLabMRReport()


class GitLabMRReport(CanaryReport):
    type = "gitlab-mr"
    description = "GitLab reporter"

    def setup_parser(self, parser: "Parser") -> None:
        sp = parser.add_subparsers(dest="action", metavar="subcommands")
        p = sp.add_parser("create", help="Create GitLab merge request reports")
        p.add_argument("--cdash-url", help="Add a link to a CDash report for this MR")
        p.add_argument(
            "-a",
            "--access-token",
            help="GitLab access token that allows to GET/POST to the merge request API",
        )

    def create(self, session: "Session | None" = None, **kwargs: Any) -> None:
        if session is None:
            raise ValueError("canary report html: session required")

        access_token = kwargs["access_token"]
        cdash_url = kwargs["cdash_url"]
        mr = MergeRequest(access_token=access_token)
        failed = group_failed_tests(session.active_cases())
        if failed:
            mr.report_failed(failed, cdash_build_url=cdash_url)
        else:
            mr.report_success(cdash_build_url=cdash_url)
        return


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

    def add_note(self, note):
        self.backend.add_note(note)

    def report_failed(
        self,
        failed_cases: dict[str, list[TestCase]],
        cdash_build_url: str | None = None,
    ):
        fp = io.StringIO()
        job = re.sub(":(build|test|report)", "", self.job_name)
        fp.write(f"Merge request pipeline `{job}` failed\n\n")

        num_failed = sum(len(_) for _ in failed_cases.values())
        sec = "<h3>Failed test summary</h3>"
        detail_threshold = 5
        if num_failed > detail_threshold:
            fp.write(f"<details>\n<summary>{sec} (click to expand)</summary>\n\n")
        else:
            fp.write(f"{sec}\n\n")
        fp.write("| Test | Status |\n| --- | --- |\n")
        for stat in failed_cases:
            for case in failed_cases[stat]:
                fp.write(f"| {case} | {stat} |\n")
        fp.write("\n")
        if num_failed > detail_threshold:
            fp.write("</details>\n\n")

        if cdash_build_url is not None:
            fp.write(f"See the [CDash entry]({cdash_build_url}) for details.\n\n")
        self.add_note(fp.getvalue())

    def report_success(self, cdash_build_url: str | None = None):
        fp = io.StringIO()
        job = re.sub(":(build|test|report)", "", self.job_name)
        fp.write(f"Merge request pipeline `{job}` finished successfully\n\n")
        if cdash_build_url is not None:
            fp.write(f"See the [CDash entry]({cdash_build_url}) for details.\n\n")
        note = fp.getvalue()
        logging.info(note)
        self.add_note(note)


def group_failed_tests(cases: list[TestCase]):
    failed: dict[str, list[TestCase]] = {}
    nonpass = ("skipped", "diffed", "failed", "timeout", "not_run", "cancelled", "unknown")
    for case in cases:
        if case.status.value in nonpass:
            failed.setdefault(case.status.value, []).append(case)
        elif case.defective():
            failed.setdefault("defective", []).append(case)
    return failed


class MissingCIVariable(Exception): ...
