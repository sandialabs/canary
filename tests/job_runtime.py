# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# ---------------------------------------------------------------------------
# Tests for job.runtime cache behavior
# ---------------------------------------------------------------------------

from pathlib import Path
from typing import Any

import pytest

import _canary.history as his
from _canary.core.job import Job
from _canary.core.jobspec import JobSpec


class FakeHistoryStore(his.HistoryStore):
    def record(self, job: Any) -> None:
        """Write a minimal job cache file with the given mean runtime."""
        spec_id, mean = job
        assert self.root is not None
        file = self.root / "jobs" / spec_id[:2] / f"{spec_id[2:]}.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(
            '{"cache": {"metrics": {"time": {"mean": %f, "min": %f, "max": %f, "variance": 0.0, "count": 1}}}}'
            % (mean, mean, mean)
        )


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "suite").mkdir()
    (root / "suite" / "test_x.py").write_text("# test file")
    return root


@pytest.fixture
def spec(repo: Path) -> JobSpec:
    return JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64, timeout=300.0)


@pytest.fixture
def space(tmp_path):
    from _canary.execution.testexec import ExecutionSpace

    sess = tmp_path / "sessions" / "s1"
    sess.mkdir(parents=True)
    return ExecutionSpace(root=sess, path=sess / "w1", session="s1")


def test_job_runtime_uses_cached_mean_when_below_timeout(spec: JobSpec, space, tmp_path):
    """A cached mean well below the timeout is used directly."""

    # find_cache_dir walks up from workspace.root (tmp_path/sessions/s1).
    # Place WORKSPACE.TAG at tmp_path so find_cache_dir resolves tmp_path/cache.
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    store = FakeHistoryStore.open(tmp_path)
    job = Job(spec=spec, workspace=space)
    store.record((spec.id, 60.0))
    assert his.estimate_runtime(job, store=store) == 60.0


def test_job_runtime_caps_stale_cache_at_timeout(spec: JobSpec, space, tmp_path):
    """A cached mean exceeding the declared timeout is capped at the timeout."""
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    store = FakeHistoryStore.open(tmp_path)
    job = Job(spec=spec, workspace=space)
    assert his.estimate_runtime(job, store=store) == his.COLD_RUNTIME_FRACTION * 300.0


def test_job_runtime_preserves_very_fast_cache(spec: JobSpec, space, tmp_path):
    """A cached mean well below the timeout is preserved."""
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    store = FakeHistoryStore.open(tmp_path)
    store.record((spec.id, 1.0))
    job = Job(spec=spec, workspace=space)
    assert his.estimate_runtime(job, store=store) == 1.0


def test_job_runtime_cap_exactly_at_timeout(spec: JobSpec, space, tmp_path):
    """A cached mean exactly equal to the timeout passes through unchanged."""
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    store = FakeHistoryStore.open(tmp_path)
    store.record((spec.id, 300.0))
    job = Job(spec=spec, workspace=space)
    assert his.estimate_runtime(job, store=store) == 300.0
