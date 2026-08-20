# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from _canary.job import Dependency
from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.testexec import ExecutionSpace


def make_job(tmp_path: Path, name: str) -> Job:
    spec = JobSpec(
        file_root=tmp_path,
        file_path=Path(f"{name}.pyt"),
        family=name,
        id=(name[0] * 64)[:64],
        timeout=10.0,
    )
    ws = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path(name), session="s1")
    return Job(spec=spec, workspace=ws)


def test_downstream_ready_after_upstream_success(tmp_path):
    upstream = make_job(tmp_path, "aaaa")
    downstream = make_job(tmp_path, "bbbb")
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    assert not downstream.is_ready()

    upstream.status.set(outcome="SUCCESS")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.is_ready()
    assert not downstream.state.is_done()


def test_downstream_blocked_after_upstream_failure(tmp_path):
    upstream = make_job(tmp_path, "aaaa")
    downstream = make_job(tmp_path, "bbbb")
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    upstream.status.set(outcome="FAILED", reason="synthetic failure")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.state.is_done()
    assert downstream.status.outcome.name == "BLOCKED"
    assert "dependency" in (downstream.status.reason or "").lower()


def test_downstream_always_ready_after_upstream_failure(tmp_path):
    upstream = make_job(tmp_path, "aaaa")
    downstream = make_job(tmp_path, "bbbb")
    downstream.dependencies.append(Dependency(job=upstream, when="always"))

    upstream.status.set(outcome="FAILED", reason="synthetic failure")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.is_ready()
    assert not downstream.state.is_done()


def test_downstream_ready_for_expected_diff(tmp_path):
    upstream = make_job(tmp_path, "aaaa")
    downstream = make_job(tmp_path, "bbbb")
    downstream.dependencies.append(Dependency(job=upstream, when="DIFFED"))

    upstream.status.set(outcome="DIFFED")
    upstream.on_finish()

    downstream.refresh_readiness()

    assert downstream.is_ready()


def test_dependency_chain_blocks_transitively(tmp_path):
    a = make_job(tmp_path, "aaaa")
    b = make_job(tmp_path, "bbbb")
    c = make_job(tmp_path, "cccc")

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
