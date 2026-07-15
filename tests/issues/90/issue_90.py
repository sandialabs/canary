# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import time
from pathlib import Path

import pytest

import _canary.config
from _canary import rerun
from _canary.job import JobPhase
from _canary.jobspec import JobSpec
from _canary.jobspec import SpecDependency
from _canary.status import Status
from _canary.workspace import Workspace


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """
    Keep this test at the library level without inheriting a caller's Canary
    environment/configuration.

    The global config object is one of the reasons these tests have historically
    used subprocesses.  For this test, we only need default configuration and the
    builtin plugins/resource manager.
    """
    monkeypatch.delenv("CANARYCFG64", raising=False)
    monkeypatch.delenv("CANARYCFGFILE", raising=False)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    monkeypatch.chdir(tmp_path)

    with _canary.config.override():
        yield


def make_abc_workspace(tmp_path: Path) -> tuple[Workspace, dict[str, JobSpec]]:
    """
    Construct this dependency graph directly:

        a -> b -> c

    This avoids parser/collector/subprocess overhead and isolates the rerun
    closure logic.
    """
    test_file = tmp_path / "test.pyt"
    test_file.write_text(
        """\
import sys
import canary

canary.directives.name("a")
canary.directives.name("b")
canary.directives.name("c")

canary.directives.depends_on("c", when="testname=b")
canary.directives.depends_on("b", when="testname=a")


def test():
    self = canary.get_instance()
    if self.name == "b":
        assert 0, "b fails"


if __name__ == "__main__":
    sys.exit(test())
"""
    )

    # Use full-length hex IDs so database partial-ID resolution is not involved.
    c = JobSpec(file_root=tmp_path, file_path=Path("test.pyt"), family="c", id="c" * 64)
    b = JobSpec(
        file_root=tmp_path,
        file_path=Path("test.pyt"),
        family="b",
        id="b" * 64,
        dependencies=[SpecDependency(spec=c, when="on_success")],
    )
    a = JobSpec(
        file_root=tmp_path,
        file_path=Path("test.pyt"),
        family="a",
        id="a" * 64,
        dependencies=[SpecDependency(spec=b, when="on_success")],
    )

    ws = Workspace.create(tmp_path)
    ws.store_specs([c, b, a])

    return ws, {"a": a, "b": b, "c": c}


def store_initial_issue_90_results(ws: Workspace, specs: dict[str, JobSpec]) -> None:
    """
    Simulate the first run:

      c passes
      b fails
      a is blocked because b failed

    We only need database state for rerun selection/closure.
    """
    session_dir = ws.sessions_dir / "initial"
    jobs = ws.construct_jobs([specs["c"], specs["b"], specs["a"]], session_dir)

    now = time.time()

    for job in jobs:
        job.state.phase = JobPhase.DONE
        job.timekeeper.submitted = now
        job.timekeeper.started = now
        job.timekeeper.finished = now + 0.1

        if job.name == "c":
            job.status = Status.SUCCESS()
        elif job.name == "b":
            job.status = Status.FAILED(reason="b fails", code=1)
        elif job.name == "a":
            job.status = Status.BLOCKED("Dependency b failed")

    ws.db.put_results(*jobs)


def test_issue_90_failed_rerun_closure_keeps_upstream_dependencies(tmp_path):
    """
    Regression test for issue 90.

    If b fails and a is blocked, rerunning failed tests must include upstream
    dependency c in the reconstructed spec set.  c should be masked so it is not
    rerun, but it must still be present so b's dependency edge can be satisfied
    from prior results.
    """
    ws, specs = make_abc_workspace(tmp_path)
    store_initial_issue_90_results(ws, specs)

    selected = rerun.get_specs(ws.db, strategy="failed")
    by_name = {spec.name: spec for spec in selected}

    assert set(by_name) == {"a", "b", "c"}

    # b failed and a was blocked/downstream, so both are runnable roots/closure.
    assert not by_name["a"].mask
    assert not by_name["b"].mask

    # c is required upstream state.  It should be present but masked.
    assert by_name["c"].mask
    assert by_name["c"].mask.reason == "Skip upstream specs"


def test_issue_90_explicit_rerun_closure_keeps_upstream_dependencies(tmp_path):
    """
    The CLI regression test used roughly:

        canary run --only=failed b

    The pathspec 'b' becomes a concrete spec-id request, and the rerun closure
    must include c as a masked upstream dependency and a as downstream work.
    """
    ws, specs = make_abc_workspace(tmp_path)
    store_initial_issue_90_results(ws, specs)

    selected = rerun.compute_rerun_closure(ws.db, roots=[specs["b"].id])
    by_name = {spec.name: spec for spec in selected}

    assert set(by_name) == {"a", "b", "c"}

    # Explicit root b and downstream a are active.
    assert not by_name["a"].mask
    assert not by_name["b"].mask

    # Upstream c is present for dependency reconstruction but will not rerun.
    assert by_name["c"].mask
    assert by_name["c"].mask.reason == "Skip upstream specs"


def test_issue_90_constructed_jobs_include_masked_upstream_result(tmp_path):
    """
    Verify that after rerun closure, Workspace.construct_jobs can still
    reconstruct b with dependency c present and carrying its previous successful
    result.
    """
    ws, specs = make_abc_workspace(tmp_path)
    store_initial_issue_90_results(ws, specs)

    selected = rerun.compute_rerun_closure(ws.db, roots=[specs["b"].id])
    jobs = ws.construct_jobs(selected, ws.sessions_dir / "rerun")
    by_name = {job.name: job for job in jobs}

    assert set(by_name) == {"a", "b", "c"}

    c = by_name["c"]
    b = by_name["b"]
    a = by_name["a"]

    assert c.mask
    assert c.status.is_success()
    assert c.state.is_done()

    assert [dep.job.name for dep in b.dependencies] == ["c"]
    assert b.dependencies[0].job.status.is_success()

    assert [dep.job.name for dep in a.dependencies] == ["b"]
