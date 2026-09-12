# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for VVT dependency matching and dependency-result expressions.

Covers:
- dependency glob matching for parameterized VVT tests
- VVT ``expect`` values: ``?``, ``+``, ``*``, and explicit integer counts
- dependency result expressions: ``pass``, ``diff``, ``fail``, ``skip``,
  ``pass or diff``, and ``*``
- correct propagation of dependency output directories to analyzer tests
"""

from pathlib import Path

import pytest

import _canary.config
from _canary.workspace import Workspace

HERE = Path(__file__).parent


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.delenv("CANARYCFG64", raising=False)
    monkeypatch.delenv("CANARYCFGFILE", raising=False)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    monkeypatch.chdir(tmp_path)

    with _canary.config.override():
        _canary.config.pluginmanager.ensure_loaded("canary_vvtest")
        yield


def collect_and_run(workspace_root: Path, vvt_file: Path):
    workspace = Workspace.create(workspace_root)
    specs = workspace.collect({str(vvt_file.parent): [vvt_file.name]})
    session = workspace.run(specs, only="all")
    return session


def test_dep_result_expressions_pass_diff_fail_outcomes(tmp_path):
    """Parameterized leaf jobs with pass/diff/fail outcomes satisfy the right analyzers."""
    session = collect_and_run(tmp_path, HERE / "dep_result_expressions_0.vvt")

    # One DIFFED bit and one FAILED bit.
    assert session.returncode == 10

    jobs_by_name = {job.name: job for job in session.jobs}

    assert jobs_by_name["demo.fruit=banana.stat=pass"].status.is_success()
    assert jobs_by_name["demo.fruit=grape.stat=diff"].status.is_diffed()
    assert jobs_by_name["demo.fruit=grapefruit.stat=fail"].status.is_failure()

    for name in (
        "demo_analyze_question",
        "demo_analyze_plus",
        "demo_analyze_int",
        "demo_analyze_star",
    ):
        assert jobs_by_name[name].status.is_success()


def test_dep_result_expressions_analyze_filters_by_result(tmp_path):
    """Analyzer-style tests triggered by specific dependency result keywords succeed."""
    session = collect_and_run(tmp_path, HERE / "dep_result_expressions_1.vvt")

    # Preserve the original regression contract: some tests intentionally fail.
    assert session.returncode == 10

    jobs_by_name = {job.name: job for job in session.jobs}

    assert jobs_by_name["foo_pass"].status.is_success()
    assert jobs_by_name["foo_diff"].status.is_diffed()
    assert jobs_by_name["foo_fail"].status.is_failure()

    # NOTE: vvtest_util.skip_exit_status is classified as FAILED in this
    # compatibility path; bar_analyze_skip is therefore BLOCKED.
    assert jobs_by_name["foo_skip"].status.is_failure()
    assert jobs_by_name["bar_analyze_skip"].status.is_blocked()

    for name in (
        "bar_analyze_pass",
        "bar_analyze_diff",
        "bar_analyze_fail",
        "bar_analyze_pass_diff",
        "bar_analyze_diff_pass",
        "bar_analyze_fail_skip",
        "bar_analyze_pass_diff_fail_skip",
        "bar_analyze_",
    ):
        assert jobs_by_name[name].status.is_success()
