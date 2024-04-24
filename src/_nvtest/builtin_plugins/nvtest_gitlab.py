import io
import os
import re
from typing import Optional

import _nvtest.plugin
from _nvtest.reporters import cdash
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import gitlab
from _nvtest.util import logging


@_nvtest.plugin.register(scope="session", stage="teardown")
def merge_request_report(session: Session) -> None:
    if "CI_MERGE_REQUEST_IID" not in os.environ:
        return
    cdash_build_url = None
    cdash_url = os.getenv("MERGE_REQUEST_CDASH_URL")
    cdash_project = os.getenv("MERGE_REQUEST_CDASH_PROJECT")
    if cdash_url and cdash_project:
        reporter = cdash.Reporter(session)
        reporter.create(
            buildname(),
            site=os.getenv("MERGE_REQUEST_CDASH_SITE"),
            track=os.getenv("MERGE_REQUEST_CDASH_TRACK", "Merge Request"),
        )
        cdash_build_url = reporter.post(cdash_url, cdash_project, *reporter.xml_files)
    try:
        mr = MergeRequest()
    except MissingCIVariable:
        return
    else:
        cases = [case for case in session.cases if not case.masked]
        failed = group_failed_tests(cases)
        if failed:
            mr.report_failed(failed, cdash_build_url=cdash_build_url)
        else:
            mr.report_success(cdash_build_url=cdash_build_url)


def buildname() -> str:
    iid = os.environ["CI_MERGE_REQUEST_IID"]
    job = os.environ["CI_JOB_NAME"]
    title = os.environ["CI_MERGE_REQUEST_TITLE"]
    return f"{title} (!{iid}), job={job}"


class MergeRequest:
    def __init__(self):
        if "GITLAB_CI" not in os.environ:
            raise MissingCIVariable("GITLAB_CI")
        for var in ("GITLAB_ACCESS_TOKEN", "ACCESS_TOKEN"):
            if var in os.environ:
                self.access_token = os.environ[var]
                break
        else:
            raise MissingCIVariable("GITLAB_ACCESS_TOKEN")
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
        cdash_build_url: Optional[str] = None,
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

    def report_success(self, cdash_build_url: Optional[str] = None):
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
    nonpass = ("skipped", "failed", "diffed", "timeout")
    for case in cases:
        if case.status.iid in nonpass:
            failed.setdefault(case.status.iid, []).append(case)
    return failed


class MissingCIVariable(Exception): ...
