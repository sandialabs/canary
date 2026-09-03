# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import types
from pathlib import Path

import pytest

from _canary.job import BaseJob
from _canary.job import Dependency
from _canary.job import Job
from _canary.job import JobPhase
from _canary.job import JobState
from _canary.job import Measurements
from _canary.jobspec import JobSpec
from _canary.jobspec import Mask
from _canary.jobspec import SpecDependency
from _canary.status import Status
from _canary.timekeeper import Timekeeper
from _canary.util import json_helper as json


def test_jobphase_values() -> None:
    assert JobPhase.PENDING.value == "PENDING"
    assert JobPhase.STAGING.value == "STAGING"
    assert JobPhase.RUNNING.value == "RUNNING"
    assert JobPhase.FINISHING.value == "FINISHING"
    assert JobPhase.DONE.value == "DONE"


def test_jobstate_defaults_to_pending() -> None:
    s = JobState()
    assert s.phase == JobPhase.PENDING
    assert s.is_pending()
    assert not s.is_running()
    assert not s.is_done()


def test_jobstate_running() -> None:
    s = JobState(phase=JobPhase.RUNNING)
    assert not s.is_pending()
    assert s.is_running()
    assert not s.is_done()


def test_jobstate_done() -> None:
    s = JobState(phase=JobPhase.DONE)
    assert not s.is_pending()
    assert not s.is_running()
    assert s.is_done()


def test_basejob_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseJob()  # type: ignore[abstract]


def test_basejob_default_phase_transitions() -> None:

    class DummyJob(BaseJob):
        id = "dummy"

        def __init__(self) -> None:
            self.state = JobState()
            self.timekeeper = Timekeeper()

        def cost(self) -> float:
            return 1.0

        @property
        def status(self) -> "Status":
            raise NotImplementedError

        def required_resources(self):
            return [{"type": "cpus", "slots": 1}]

        def assign_resources(self, arg):
            self._resources = arg

        def free_resources(self):
            return getattr(self, "_resources", {})

        def refresh_readiness(self) -> None:
            return

        def is_runnable(self) -> bool:
            return True

        def is_ready(self) -> bool:
            return True

        def total_timeout(self) -> float:
            return 1.0

        def refresh(self) -> None:
            return

        def save(self) -> None:
            return

        def display_name(self, **kwargs) -> str:
            return "DummyJob"

    job = DummyJob()
    assert job.state.phase == JobPhase.PENDING

    job.on_start()
    assert job.state.phase == JobPhase.RUNNING

    job.on_finish()
    assert job.state.phase == JobPhase.DONE


def test_basejob_validate_enqueuable_rejects_running_or_done() -> None:
    class DummyJob(BaseJob):
        id = "dummy"

        def __init__(self, phase: JobPhase) -> None:
            self.state = JobState(phase=phase)
            self.timekeeper = Timekeeper()

        def cost(self) -> float:
            return 1.0

        @property
        def status(self) -> "Status":
            raise NotImplementedError

        def required_resources(self):
            return [{"type": "cpus", "slots": 1}]

        def assign_resources(self, arg):
            self._resources = arg

        def free_resources(self):
            return getattr(self, "_resources", {})

        def refresh_readiness(self) -> None:
            return

        def is_runnable(self) -> bool:
            return True

        def is_ready(self) -> bool:
            return True

        def total_timeout(self) -> float:
            return 1.0

        def refresh(self) -> None:
            return

        def save(self) -> None:
            return

        def display_name(self, **kwargs) -> str:
            return "DummyJob"

    pending = DummyJob(JobPhase.PENDING)
    pending.validate_enqueuable()  # should not raise

    running = DummyJob(JobPhase.RUNNING)
    with pytest.raises(ValueError):
        running.validate_enqueuable()

    done = DummyJob(JobPhase.DONE)
    with pytest.raises(ValueError):
        done.validate_enqueuable()


class DummyLauncher:
    def run(self, job=None, case=None):
        return 0


@pytest.fixture(autouse=True)
def _patch_pluginmanager_and_config(monkeypatch):
    """
    Job.__init__ relies on config.pluginmanager.hook for:
      - canary_runtest_launcher
      - canary_resource_pool_types
      - canary_resource_pool_count_per_node
    and on config.get/config.getoption/config.serialize in a few methods.
    """
    from _canary import config

    hook = types.SimpleNamespace(
        canary_runtest_launcher=lambda case=None, job=None: DummyLauncher(),
        canary_resource_pool_types=lambda: ["cpus", "gpus"],
        canary_resource_pool_count_per_node=lambda type="cpu": 1,
    )
    monkeypatch.setattr(config, "pluginmanager", types.SimpleNamespace(hook=hook), raising=True)
    monkeypatch.setattr(config, "getoption", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(config, "get", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(config, "serialize", lambda: "CFG", raising=True)


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
    from _canary.testexec import ExecutionSpace

    sess = tmp_path / "sessions" / "s1"
    sess.mkdir(parents=True)
    return ExecutionSpace(root=sess, path=sess / "w1", session="s1")


def test_jobphase_roundtrip_json():
    out = json.loads(json.dumps(JobPhase.RUNNING))
    assert out == JobPhase.RUNNING


def test_jobstate_roundtrip_json():
    st = JobState(phase=JobPhase.STAGING)
    out = json.loads(json.dumps(st))
    assert out == st
    assert out.phase == JobPhase.STAGING


def test_measurements_roundtrip_json():
    m = Measurements(data={"a": 1, "b": "x"})
    out = json.loads(json.dumps(m))
    assert out == m


def test_job_minimal_construction(spec: JobSpec, space):
    job = Job(spec=spec, workspace=space)
    assert job.id == spec.id
    assert job.state.phase == JobPhase.PENDING
    assert job.status is not None
    assert job.timekeeper is not None
    assert job.measurements is not None
    assert isinstance(job.variables, dict)


def test_job_mask_override(spec: JobSpec, space):
    assert bool(spec.mask) is False
    job = Job(spec=spec, workspace=space)
    assert bool(job.mask) is False
    job.mask = Mask.masked("nope")
    assert bool(job.mask) is True
    assert job.mask.reason == "nope"


def test_dependency_roundtrip_json(spec: JobSpec, space):
    j = Job(spec=spec, workspace=space)
    dep = Dependency(job=j, when="on_success")
    out = json.loads(json.dumps(dep))
    assert out.when == dep.when
    assert isinstance(out.job, Job)
    assert out.job.id == j.id


def test_job_roundtrip_json_includes_base_state(spec: JobSpec, space):
    job = Job(spec=spec, workspace=space)
    job.state.phase = JobPhase.RUNNING
    job.status.set(category="PASS", outcome="SUCCESS", reason=None, code=0)
    job.measurements.add_measurement("x", 2)
    job.timekeeper.open(at=1.0)
    job.timekeeper.stage(at=1.5)
    job.timekeeper.start(at=2.0)
    job.timekeeper.stop(at=2.5)
    job.timekeeper.close(at=3.0)
    job.variables["FOO"] = "BAR"
    job._allocation = {"metadata": {}, "resources": {"cpus": [{"id": "0", "slots": 1}]}}

    out = json.loads(json.dumps(job))
    assert isinstance(out, Job)
    assert out.id == job.id
    assert out.state.phase == JobPhase.RUNNING
    assert out.status.category == job.status.category
    assert out.measurements.data["x"] == 2
    assert out.timekeeper._finished == 3.0
    assert out.variables["FOO"] == "BAR"
    assert out.resources == {"cpus": [{"id": "0", "slots": 1}]}


def test_job_dependency_graph_roundtrip_json(repo: Path, space, tmp_path):
    """
    Ensure a Job with dependencies serializes and loads without errors.
    (Note: this will duplicate the dependent Job object; if you later want
    identity preservation, you'll need an id-based scheme.)
    """
    f = Path("suite/test_x.py")
    spec_a = JobSpec(file_root=repo, file_path=f, id="a" * 64, family="a", timeout=10.0)
    spec_b = JobSpec(file_root=repo, file_path=f, id="b" * 64, family="b", timeout=10.0)

    # Spec-level dependency (b depends on a)
    spec_b.dependencies.append(SpecDependency(spec=spec_a, when="on_success"))

    job_a = Job(spec=spec_a, workspace=space)
    job_b = Job(
        spec=spec_b, workspace=space, dependencies=[Dependency(job=job_a, when="on_success")]
    )

    out = json.loads(json.dumps(job_b))
    assert isinstance(out, Job)
    assert out.dependencies[0].when == "on_success"
    assert out.dependencies[0].job.id == job_a.id


def test_job_save_uses_atomic_tmp_cleanup(spec: JobSpec, space):
    job = Job(spec=spec, workspace=space)
    job.status.set(outcome="SUCCESS")

    job.save()

    assert job.lockfile.exists()
    assert not (job.lockfile.parent / f".{job.lockfile.name}.tmp").exists()

    loaded = json.loads(job.lockfile.read_text())
    assert loaded.id == job.id


# ---------------------------------------------------------------------------
# Tests for job.runtime clamping (cap + floor)
# ---------------------------------------------------------------------------

def _write_job_cache(cache_dir: Path, spec_id: str, mean: float) -> None:
    """Write a minimal job cache file with the given mean runtime."""
    file = cache_dir / "jobs" / spec_id[:2] / f"{spec_id[2:]}.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        '{"cache": {"metrics": {"time": {"mean": %f, "min": %f, "max": %f, "variance": 0.0, "count": 1}}}}' % (mean, mean, mean)
    )


def test_job_runtime_falls_back_to_timeout_when_no_cache(spec: JobSpec, space):
    """When there is no job cache, runtime should equal the declared timeout."""
    job = Job(spec=spec, workspace=space)
    assert job.runtime == spec.timeout


def test_job_runtime_uses_cached_mean_when_below_timeout(spec: JobSpec, space, tmp_path):
    """A cached mean well below the timeout is used directly (subject to floor)."""
    from _canary.job import _RUNTIME_FLOOR_FRACTION

    # find_cache_dir walks up from workspace.root (tmp_path/sessions/s1).
    # Place WORKSPACE.TAG at tmp_path so find_cache_dir resolves tmp_path/cache.
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    _write_job_cache(tmp_path / "cache", spec.id, mean=60.0)

    job = Job(spec=spec, workspace=space)
    # floor = 300 * 0.1 = 30s; mean=60 > floor and < timeout → use 60
    assert job.runtime == 60.0


def test_job_runtime_caps_stale_cache_at_timeout(spec: JobSpec, space, tmp_path):
    """A cached mean exceeding the declared timeout is capped at the timeout."""
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    _write_job_cache(tmp_path / "cache", spec.id, mean=900.0)  # stale: 900s > 300s timeout

    job = Job(spec=spec, workspace=space)
    assert job.runtime == spec.timeout  # capped at 300.0


def test_job_runtime_floors_very_fast_cache(spec: JobSpec, space, tmp_path):
    """A cached mean well below the floor is raised to timeout * floor_fraction."""
    from _canary.job import _RUNTIME_FLOOR_FRACTION

    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    _write_job_cache(tmp_path / "cache", spec.id, mean=1.0)  # 1s actual on 300s declared job

    job = Job(spec=spec, workspace=space)
    expected_floor = spec.timeout * _RUNTIME_FLOOR_FRACTION  # 30.0
    assert job.runtime == expected_floor


def test_job_runtime_cap_exactly_at_timeout(spec: JobSpec, space, tmp_path):
    """A cached mean exactly equal to the timeout passes through unchanged."""
    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    _write_job_cache(tmp_path / "cache", spec.id, mean=300.0)

    job = Job(spec=spec, workspace=space)
    assert job.runtime == 300.0


def test_job_runtime_stale_cache_logs_debug(spec: JobSpec, space, tmp_path, caplog):
    """A stale cached mean (> timeout) emits a debug-level log message."""
    import logging
    import _canary.job as job_module

    (tmp_path / "WORKSPACE.TAG").write_text("Signature: test\n")
    _write_job_cache(tmp_path / "cache", spec.id, mean=750.0)  # 2.5x the 300s timeout

    # Reset the once-per-process log flag so this test is order-independent.
    job_module._cache_dir_logged = False

    with caplog.at_level(logging.DEBUG, logger="_canary.job"):
        job = Job(spec=spec, workspace=space)
        _ = job.runtime  # trigger cached_property

    assert any("exceeds declared timeout" in r.message for r in caplog.records)
