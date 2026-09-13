# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for rerun closure computation with upstream/downstream dependencies.

Verifies that when a job fails and a downstream job is blocked, rerunning
failed tests correctly includes upstream dependency specs (masked, to supply
prior results) and downstream specs (active, to be re-executed).
"""

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
    monkeypatch.delenv("CANARYCFG64", raising=False)
    monkeypatch.delenv("CANARYCFGFILE", raising=False)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    monkeypatch.chdir(tmp_path)

    with _canary.config.override():
        yield


def make_linear_dep_workspace(tmp_path: Path) -> tuple[Workspace, dict[str, JobSpec]]:
    """Construct the dependency graph ``a -> b -> c`` directly without parsing."""
    test_file = tmp_path / "test.pyt"
    test_file.write_text(
        """\
import sys
import canary_pyt

canary_pyt.directives.name("a")
canary_pyt.directives.name("b")
canary_pyt.directives.name("c")

canary_pyt.directives.depends_on("c", when="testname=b")
canary_pyt.directives.depends_on("b", when="testname=a")


def test():
    self = canary.get_instance()
    if self.name == "b":
        assert 0, "b fails"


if __name__ == "__main__":
    sys.exit(test())
"""
    )

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


def store_initial_results(ws: Workspace, specs: dict[str, JobSpec]) -> None:
    """Simulate: c passes, b fails, a is blocked."""
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


def test_rerun_failed_includes_upstream_as_masked(tmp_path):
    """rerun strategy='failed' includes upstream c as masked and b/a as active."""
    ws, specs = make_linear_dep_workspace(tmp_path)
    store_initial_results(ws, specs)

    selected = rerun.get_specs(ws.db, strategy="failed")
    by_name = {spec.name: spec for spec in selected}

    assert set(by_name) == {"a", "b", "c"}

    assert not by_name["a"].mask
    assert not by_name["b"].mask

    assert by_name["c"].mask
    assert by_name["c"].mask.reason == "Skip upstream specs"


def test_rerun_explicit_root_includes_upstream_masked_and_downstream_active(tmp_path):
    """Explicit rerun of b includes c (masked upstream) and a (downstream)."""
    ws, specs = make_linear_dep_workspace(tmp_path)
    store_initial_results(ws, specs)

    selected = rerun.compute_rerun_closure(ws.db, roots=[specs["b"].id])
    by_name = {spec.name: spec for spec in selected}

    assert set(by_name) == {"a", "b", "c"}

    assert not by_name["a"].mask
    assert not by_name["b"].mask

    assert by_name["c"].mask
    assert by_name["c"].mask.reason == "Skip upstream specs"


def test_rerun_constructed_jobs_carry_prior_upstream_result(tmp_path):
    """After rerun closure, construct_jobs gives c its prior SUCCESS status."""
    ws, specs = make_linear_dep_workspace(tmp_path)
    store_initial_results(ws, specs)

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
