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
from _canary.util import json_helper as json


def test_jobphase_values() -> None:
    assert JobPhase.PENDING.value == "PENDING"
    assert JobPhase.SUBMITTED.value == "SUBMITTED"
    assert JobPhase.RUNNING.value == "RUNNING"
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
        # Satisfy BaseJob abstract interface as loosely as possible for this test.
        id = "dummy"

        def __init__(self) -> None:
            self.state = JobState()

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

    job.on_started()
    assert job.state.phase == JobPhase.RUNNING

    job.on_finished()
    assert job.state.phase == JobPhase.DONE


def test_basejob_validate_enqueuable_rejects_running_or_done() -> None:
    class DummyJob(BaseJob):
        id = "dummy"

        def __init__(self, phase: JobPhase) -> None:
            self.state = JobState(phase=phase)

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
    return JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64)


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
    st = JobState(phase=JobPhase.SUBMITTED)
    out = json.loads(json.dumps(st))
    assert out == st
    assert out.phase == JobPhase.SUBMITTED


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
    job.timekeeper.submitted = 1.0
    job.timekeeper.started = 2.0
    job.timekeeper.finished = 3.0
    job.variables["FOO"] = "BAR"
    job._resources = {"cpus": [{"id": "0", "slots": 1}]}

    out = json.loads(json.dumps(job))
    assert isinstance(out, Job)
    assert out.id == job.id
    assert out.state.phase == JobPhase.RUNNING
    assert out.status.category == job.status.category
    assert out.measurements.data["x"] == 2
    assert out.timekeeper.finished == 3.0
    assert out.variables["FOO"] == "BAR"
    assert out.resources == {"cpus": [{"id": "0", "slots": 1}]}


def test_job_dependency_graph_roundtrip_json(repo: Path, space, tmp_path):
    """
    Ensure a Job with dependencies serializes and loads without errors.
    (Note: this will duplicate the dependent Job object; if you later want
    identity preservation, you'll need an id-based scheme.)
    """
    spec_a = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64, family="a")
    spec_b = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="b" * 64, family="b")

    # Spec-level dependency (b depends on a)
    spec_b.dependencies.append(SpecDependency(spec=spec_a, when="on_success"))

    job_a = Job(spec=spec_a, workspace=space)
    job_b = Job(
        spec=spec_b, workspace=space, dependencies=[Dependency(job=job_a, when="on_success")]
    )

    out = json.loads(json.dumps(job_b))
    assert isinstance(out, Job)
    assert out.depends_on[0].when == "on_success"
    assert out.depends_on[0].job.id == job_a.id
