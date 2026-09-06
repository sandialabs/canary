# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
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
from _canary.reporters.reporter import running_in_ci
from _canary.status import Status
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    from _canary import config

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
        with config.override():
            setattr(config.options, "report", None)
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


@pytest.mark.skipif(running_in_ci(), reason="Skip test in CI")
def test_workspace_html_report_not_created_by_default(setup):
    report = setup.workspace_path / "reports" / "html" / "index.html"
    total = setup.workspace_path / "reports" / "html" / "Total.html"
    manifest = setup.workspace_path / "reports" / "html" / "manifest.json"
    summary = setup.tmp_path / "Canary.html"

    assert not report.exists()
    assert not total.exists()
    assert not manifest.exists()
    assert not summary.exists()


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


def test_fmt_secs_negative_is_na():
    from _canary.reporter import fmt_secs

    assert fmt_secs(-1.0) == "NA"
    assert fmt_secs(-0.001) == "NA"
    assert fmt_secs(-5.0, na="--") == "--"


def test_fmt_secs_seconds_tier():
    from _canary.reporter import fmt_secs

    # < 600s: seconds with one decimal (fixed width matches legacy format)
    assert fmt_secs(0.0) == "  0.0s"
    assert fmt_secs(1.0) == "  1.0s"
    assert fmt_secs(123.4) == "123.4s"
    assert fmt_secs(599.9) == "599.9s"


def test_fmt_secs_minutes_tier():
    from _canary.reporter import fmt_secs

    # [600, 3600): whole minutes and seconds
    assert fmt_secs(600.0) == "10m 00s"
    assert fmt_secs(723.0) == "12m 03s"
    assert fmt_secs(3599.0) == "59m 59s"


def test_fmt_secs_hours_tier():
    from _canary.reporter import fmt_secs

    # >= 3600: whole hours and minutes
    assert fmt_secs(3600.0) == "1h 00m"
    assert fmt_secs(3900.0) == "1h 05m"
    assert fmt_secs(7200.0) == "2h 00m"
    assert fmt_secs(45296.0) == "12h 34m"


def test_fmt_secs_tier_boundaries():
    from _canary.reporter import fmt_secs

    # Exact boundaries switch units.
    assert "m" not in fmt_secs(599.99)
    assert fmt_secs(600.0) == "10m 00s"
    assert fmt_secs(3600.0) == "1h 00m"
