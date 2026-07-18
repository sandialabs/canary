# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from _canary.job import Job
from _canary.reporters.html import HTMLReporter
from _canary.reporters.html import HTMLReportRequest
from _canary.reporters.json import JsonReporter
from _canary.reporters.json import JsonReportRequest
from _canary.reporters.junit import JunitReporter
from _canary.reporters.junit import JunitReportRequest
from _canary.reporters.markdown import MarkdownReporter
from _canary.reporters.markdown import MarkdownReportRequest
from _canary.status import Status
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("canary-reporter")

    with working_dir(root):
        for name in ("test_one.pyt", "test_two.pyt"):
            with open(name, "w") as fh:
                fh.write(
                    """\
import canary

def test():
    pass

if __name__ == "__main__":
    test()
"""
                )

        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        session = workspace.run(specs, only="all")

        ns = SimpleNamespace(
            tmp_path=root,
            workspace=workspace,
            workspace_path=root / ".canary",
            reports_path=root / ".canary" / "reports",
            results_path=root / "TestResults",
            session=session,
        )
        yield ns


def load_manifest(path: Path) -> dict:
    with open(path) as fh:
        return json.load(fh)


def latest_jobs(workspace: Workspace) -> list[Job]:
    jobs = workspace.load_jobs()
    assert jobs
    return jobs


def test_workspace_html_report_created_by_run(setup):
    """A normal run should create a workspace-level HTML report."""
    report = setup.workspace_path / "reports" / "html" / "index.html"
    total = setup.workspace_path / "reports" / "html" / "Total.html"
    manifest = setup.workspace_path / "reports" / "html" / "manifest.json"
    summary = setup.tmp_path / "Canary.html"

    assert report.exists()
    assert total.exists()
    assert manifest.exists()
    assert summary.exists()

    if summary.is_symlink():
        target = os.readlink(summary)
        assert target == os.path.join(".canary", "reports", "html", "index.html")


def test_junit_report(setup):
    jobs = latest_jobs(setup.workspace)
    output = setup.tmp_path / "junit.xml"

    JunitReporter().write(JunitReportRequest(workspace=setup.workspace, jobs=jobs, output=output))

    assert output.exists()


def test_junit_report_custom_output(setup):
    jobs = latest_jobs(setup.workspace)
    output = setup.tmp_path / "junit-create.xml"

    JunitReporter().write(JunitReportRequest(workspace=setup.workspace, jobs=jobs, output=output))

    assert output.exists()


def test_json_report(setup):
    jobs = latest_jobs(setup.workspace)
    output = setup.tmp_path / "canary.json"

    JsonReporter().write(JsonReportRequest(workspace=setup.workspace, jobs=jobs, output=output))

    assert output.exists()


def test_json_report_custom_output(setup):
    jobs = latest_jobs(setup.workspace)
    output = setup.tmp_path / "canary-create.json"

    JsonReporter().write(JsonReportRequest(workspace=setup.workspace, jobs=jobs, output=output))

    assert output.exists()


def test_html_report(setup):
    jobs = latest_jobs(setup.workspace)
    output_dir = setup.tmp_path / "HTML"

    HTMLReporter().write(
        HTMLReportRequest(workspace=setup.workspace, jobs=jobs, output_dir=output_dir)
    )

    assert (output_dir / "index.html").exists()
    assert (output_dir / "Total.html").exists()
    assert (output_dir / "manifest.json").exists()


def test_html_report_custom_output_dir(setup):
    jobs = latest_jobs(setup.workspace)
    output_dir = setup.tmp_path / "MYHTML"

    HTMLReporter().write(
        HTMLReportRequest(workspace=setup.workspace, jobs=jobs, output_dir=output_dir)
    )

    assert (output_dir / "index.html").exists()
    assert (output_dir / "Total.html").exists()
    assert (output_dir / "manifest.json").exists()


def test_html_report_updates_in_place(setup):
    jobs = latest_jobs(setup.workspace)
    output_dir = setup.tmp_path / "UPDATE_HTML"

    reporter = HTMLReporter()
    reporter.write(HTMLReportRequest(workspace=setup.workspace, jobs=jobs, output_dir=output_dir))

    manifest_path = output_dir / "manifest.json"
    before = load_manifest(manifest_path)
    assert len(before) == len(jobs)

    updated = jobs[0]
    updated.status = Status.FAILED(reason="synthetic failure for report update test")
    reporter.write(
        HTMLReportRequest(workspace=setup.workspace, jobs=[updated], output_dir=output_dir)
    )

    after = load_manifest(manifest_path)
    assert len(after) == len(before)
    assert after[updated.id]["status"] == "FAILED"
    assert after[updated.id]["group"] == "Fail"

    for job in jobs[1:]:
        assert job.id in after
        assert after[job.id]["status"] == before[job.id]["status"]


def test_markdown_report(setup):
    jobs = latest_jobs(setup.workspace)
    output_dir = setup.tmp_path / "MARKDOWN"

    MarkdownReporter().write(
        MarkdownReportRequest(workspace=setup.workspace, jobs=jobs, output_dir=output_dir)
    )

    assert (output_dir / "index.md").exists()
    assert (output_dir / "Total.md").exists()
    assert (output_dir / "manifest.json").exists()


def test_markdown_report_custom_output_dir(setup):
    jobs = latest_jobs(setup.workspace)
    output_dir = setup.tmp_path / "MYMARKDOWN"

    MarkdownReporter().write(
        MarkdownReportRequest(workspace=setup.workspace, jobs=jobs, output_dir=output_dir)
    )

    assert (output_dir / "index.md").exists()
    assert (output_dir / "Total.md").exists()
    assert (output_dir / "manifest.json").exists()


def test_markdown_report_updates_in_place(setup):
    jobs = latest_jobs(setup.workspace)
    output_dir = setup.tmp_path / "UPDATE_MARKDOWN"

    reporter = MarkdownReporter()
    reporter.write(
        MarkdownReportRequest(workspace=setup.workspace, jobs=jobs, output_dir=output_dir)
    )

    manifest_path = output_dir / "manifest.json"
    before = load_manifest(manifest_path)
    assert len(before) == len(jobs)

    updated = jobs[0]
    updated.status = Status.FAILED(reason="synthetic failure for report update test")
    reporter.write(
        MarkdownReportRequest(workspace=setup.workspace, jobs=[updated], output_dir=output_dir)
    )

    after = load_manifest(manifest_path)
    assert len(after) == len(before)
    assert after[updated.id]["status"] == "FAILED"
    assert after[updated.id]["group"] == "Fail"

    for job in jobs[1:]:
        assert job.id in after
        assert after[job.id]["status"] == before[job.id]["status"]
