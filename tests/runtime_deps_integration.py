# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Unit tests for runtime dependency resolution and database persistence.

These tests replaced a set of integration tests that exercised the same
logic through full workspace.run() subprocess runs (costing ~8s total).
The dependency-resolution logic is tested at the Job/Dependency layer
directly; subprocess execution is not required.

The integration-level duplicate of blocking/always/diffed/transitive
behaviour is already covered in runtime_deps.py.  This file retains only
tests that verify behaviour unique to the database-persistence layer and
adds extra coverage of dependency scenarios that were only tested at the
integration level before.
"""

from pathlib import Path

import canary
from _canary.job import Dependency
from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.testexec import ExecutionSpace
from _canary.workspace import Workspace


def make_job(tmp_path: Path, name: str, timeout: float = 10.0) -> Job:
    spec = JobSpec(
        file_root=tmp_path,
        file_path=Path(f"{name}.pyt"),
        family=name,
        id=(name[0] * 64)[:64],
        timeout=timeout,
    )
    ws = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path(name), session="s1")
    return Job(spec=spec, workspace=ws)


# ---------------------------------------------------------------------------
# Dependency resolution — integration-level scenarios not in runtime_deps.py
# ---------------------------------------------------------------------------


def test_downstream_blocks_when_success_dependency_fails(tmp_path):
    """BLOCKED outcome is set and state is done when upstream FAILS."""
    upstream = make_job(tmp_path, "upstream")
    downstream = make_job(tmp_path, "downstream")
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    upstream.status.set(outcome="FAILED", reason="synthetic upstream failure")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.state.is_done()
    assert downstream.status.outcome.name == "BLOCKED"
    assert "dependency" in (downstream.status.reason or "").lower()


def test_downstream_runs_when_dependency_is_always(tmp_path):
    """when='always' allows downstream to run even when upstream FAILED."""
    upstream = make_job(tmp_path, "upstream")
    downstream = make_job(tmp_path, "downstream")
    downstream.dependencies.append(Dependency(job=upstream, when="always"))

    upstream.status.set(outcome="FAILED", reason="synthetic upstream failure")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.is_ready()
    assert not downstream.state.is_done()


def test_downstream_runs_for_expected_diff_dependency(tmp_path):
    """when='DIFFED' allows downstream to run when upstream produced a diff."""
    upstream = make_job(tmp_path, "upstream")
    downstream = make_job(tmp_path, "downstream")
    downstream.dependencies.append(Dependency(job=upstream, when="DIFFED"))

    upstream.status.set(outcome="DIFFED")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.is_ready()
    assert not downstream.state.is_done()


def test_blocking_is_transitive(tmp_path):
    """BLOCKED status propagates through a dependency chain a→b→c."""
    a = make_job(tmp_path, "a")
    b = make_job(tmp_path, "b")
    c = make_job(tmp_path, "c")

    b.dependencies.append(Dependency(job=a, when="on_success"))
    c.dependencies.append(Dependency(job=b, when="on_success"))

    a.status.set(outcome="FAILED", reason="synthetic failure")
    a.on_finish()

    b.refresh_readiness()
    assert b.state.is_done()
    assert b.status.outcome.name == "BLOCKED"

    c.refresh_readiness()
    assert c.state.is_done()
    assert c.status.outcome.name == "BLOCKED"


# ---------------------------------------------------------------------------
# Database persistence — unique to this file
# ---------------------------------------------------------------------------


def test_blocked_jobs_are_persisted_to_database(tmp_path):
    """A BLOCKED job written via db.put_results() is recoverable via get_results()."""
    root = tmp_path / "workspace"
    root.mkdir()

    with canary.config.override():
        workspace = Workspace.create(root)

    upstream = make_job(root, "upstream")
    downstream = make_job(root, "downstream")
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    upstream.status.set(outcome="FAILED", reason="synthetic upstream failure")
    upstream.on_finish()

    downstream.refresh_readiness()
    assert downstream.status.outcome.name == "BLOCKED"

    # Persist specs so get_results can find them.
    workspace.db.put_specs([upstream.spec, downstream.spec])
    workspace.db.put_results(upstream, downstream)

    results = workspace.db.get_results()

    assert downstream.id in results
    assert results[downstream.id]["status"].outcome.name == "BLOCKED"


def test_downstream_reason_mentions_dependency(tmp_path):
    """The BLOCKED reason string identifies the blocking dependency."""
    upstream = make_job(tmp_path, "upstream")
    downstream = make_job(tmp_path, "downstream")
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    upstream.status.set(outcome="FAILED", reason="boom")
    upstream.on_finish()
    downstream.refresh_readiness()

    assert "dependency" in (downstream.status.reason or "").lower()


def test_multiple_upstreams_all_must_pass(tmp_path):
    """A job with two on_success deps is BLOCKED when either upstream fails."""
    up1 = make_job(tmp_path, "up1")
    up2 = make_job(tmp_path, "up2")
    downstream = make_job(tmp_path, "downstream")
    downstream.dependencies.append(Dependency(job=up1, when="on_success"))
    downstream.dependencies.append(Dependency(job=up2, when="on_success"))

    up1.status.set(outcome="SUCCESS")
    up1.on_finish()
    up2.status.set(outcome="FAILED", reason="second upstream failed")
    up2.on_finish()

    downstream.refresh_readiness()

    assert downstream.state.is_done()
    assert downstream.status.outcome.name == "BLOCKED"


def test_downstream_not_ready_until_upstream_finishes(tmp_path):
    """is_ready() returns False until the upstream has finished."""
    upstream = make_job(tmp_path, "upstream")
    downstream = make_job(tmp_path, "downstream")
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    # Upstream set to SUCCESS but not finished yet.
    upstream.status.set(outcome="SUCCESS")
    downstream.refresh_readiness()
    assert not downstream.is_ready()

    upstream.on_finish()
    downstream.refresh_readiness()
    assert downstream.is_ready()
