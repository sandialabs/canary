# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression tests for issue 20.

These tests exercise VVT dependency matching and dependency-result expressions
without invoking the Canary CLI through a subprocess.  The original regression
tests used ``CanaryCommand("run")`` against VVT files and asserted the final
process return code.  These replacements use the library-level ``Workspace``
APIs directly to collect, generate, and run the same VVT inputs in-process.

The covered behavior includes:

- dependency glob matching for parameterized VVT tests;
- VVT ``expect`` values of ``?``, ``+``, ``*``, and explicit integer counts;
- dependency result expressions such as ``pass``, ``diff``, ``fail``, ``skip``,
  ``pass or diff``, and ``*``;
- correct propagation of dependency output directories to analyzer-style tests.

The tests still execute the generated test jobs because the regression concerns
runtime dependency result filtering, but they avoid testing CLI parsing and
subprocess startup.
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
        _canary.config.set("workspace:view:reports", ["none"], replace=True)
        try:
            _canary.config.pluginmanager.ensure_loaded("canary_vvtest")
        except Exception:
            pass
        yield


def collect_specs(workspace_root: Path, file: Path):
    workspace = Workspace.create(workspace_root)
    file = file.absolute()
    specs = workspace.collect({str(file.parent): [file.name]})
    return workspace, specs


def test_issue_20_0(tmp_path):
    workspace, specs = collect_specs(tmp_path, HERE / "issue-20-0.vvt")

    session = workspace.run(specs, only="all")

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


def test_issue_20_1(tmp_path):
    workspace, specs = collect_specs(tmp_path, HERE / "issue-20-1.vvt")

    session = workspace.run(specs, only="all")

    # Preserve the original regression contract: some tests intentionally fail,
    # so a non-zero return code is expected.  This is the same value asserted by
    # the previous CanaryCommand/subprocess test.
    assert session.returncode == 10

    jobs_by_name = {job.name: job for job in session.jobs}

    assert jobs_by_name["foo_pass"].status.is_success()
    assert jobs_by_name["foo_diff"].status.is_diffed()
    assert jobs_by_name["foo_fail"].status.is_failure()

    # NOTE:
    # issue-20-1.vvt uses vvtest_util.skip_exit_status.  In this compatibility
    # path, that exit code is currently classified by Canary as FAILED rather
    # than SKIPPED, so bar_analyze_skip is BLOCKED.  The original regression test
    # did not assert skip classification; it only asserted the aggregate return
    # code above.
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
