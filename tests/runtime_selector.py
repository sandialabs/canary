# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from _canary.core.job import Job
from _canary.core.jobspec import JobSpec
from _canary.core.rules import RerunRule
from _canary.core.rules import RuleOutcome
from _canary.core.rules import RuntimeRule
from _canary.execution.testexec import ExecutionSpace
from _canary.select import RuntimeSelector


class RejectNamed(RuntimeRule):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    @property
    def default_reason(self) -> str:
        return f"reject {self.name}"

    def __call__(self, job: Job) -> RuleOutcome:
        if job.name == self.name:
            return RuleOutcome.failed(self.default_reason)
        return RuleOutcome(True)


def make_job(tmp_path: Path, name: str) -> Job:
    spec = JobSpec(
        file_root=tmp_path, file_path=Path(f"{name}.pyt"), family=name, id=(name[0] * 64)[:64]
    )
    workspace = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path(name), session="s1")
    return Job(spec=spec, workspace=workspace)


def test_runtime_selector_applies_custom_rule(tmp_path):
    jobs = [make_job(tmp_path, "a"), make_job(tmp_path, "b")]

    selector = RuntimeSelector(jobs, workspace=tmp_path)
    selector.add_rule(RejectNamed("b"))
    selector.run()

    assert not jobs[0].mask
    assert jobs[1].mask
    assert "reject b" in (jobs[1].mask.reason or "")


def test_rerun_rule_not_pass_selects_failed_but_not_success(tmp_path):
    good = make_job(tmp_path, "a")
    bad = make_job(tmp_path, "b")

    good.status.set(outcome="SUCCESS")
    bad.status.set(outcome="FAILED")

    selector = RuntimeSelector([good, bad], workspace=tmp_path)
    selector.add_rule(RerunRule("not_pass"))
    selector.run()

    assert good.mask
    assert not bad.mask


def test_rerun_rule_all_selects_all(tmp_path):
    good = make_job(tmp_path, "a")
    bad = make_job(tmp_path, "b")

    good.status.set(outcome="SUCCESS")
    bad.status.set(outcome="FAILED")

    selector = RuntimeSelector([good, bad], workspace=tmp_path)
    selector.add_rule(RerunRule("all"))
    selector.run()

    assert not good.mask
    assert not bad.mask


def test_rerun_rule_ids_selects_only_matching_ids(tmp_path):
    a = make_job(tmp_path, "a")
    b = make_job(tmp_path, "b")

    selector = RuntimeSelector([a, b], workspace=tmp_path)
    selector.add_rule(RerunRule(f"ids:{a.id}"))
    selector.run()

    assert not a.mask
    assert b.mask


def make_dependent_pair(tmp_path: Path) -> tuple[Job, Job]:
    from _canary.core.job import Dependency

    upstream = make_job(tmp_path, "u")
    spec = JobSpec(file_root=tmp_path, file_path=Path("d.pyt"), family="d", id=("d" * 64)[:64])
    workspace = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path("d"), session="s1")
    dependent = Job(
        spec=spec, workspace=workspace, dependencies=[Dependency(job=upstream, when=None)]
    )
    return upstream, dependent


def test_masked_upstream_in_progress_masks_dependent(tmp_path):
    from _canary.core.job import JobPhase
    from _canary.core.jobspec import Mask

    upstream, dependent = make_dependent_pair(tmp_path)
    upstream.mask = Mask.masked(reason="not in this run")
    upstream.state.phase = JobPhase.RUNNING

    selector = RuntimeSelector([upstream, dependent], workspace=tmp_path)
    selector.run()

    assert dependent.mask


def test_refresh_masked_jobs_loads_upstream_state_from_lockfile(tmp_path):
    from _canary.core.job import JobPhase
    from _canary.core.jobspec import Mask
    from _canary.session.workspace import Workspace

    upstream, dependent = make_dependent_pair(tmp_path)

    # The upstream ran elsewhere and recorded its result in its lock file.
    upstream.workspace.dir.mkdir(parents=True)
    upstream.state.phase = JobPhase.DONE
    upstream.status.set(outcome="SUCCESS")
    upstream.save()

    # The copy loaded from the database has not caught up yet.
    upstream.state.phase = JobPhase.RUNNING
    upstream.status.reset()
    upstream.mask = Mask.masked(reason="not in this run")

    Workspace.refresh_masked_jobs([upstream, dependent])
    assert upstream.state.is_done()
    assert upstream.status.is_success()

    selector = RuntimeSelector([upstream, dependent], workspace=tmp_path)
    selector.run()

    assert not dependent.mask
    assert dependent.is_ready()


def test_refresh_masked_jobs_ignores_unmasked_and_missing_lockfiles(tmp_path):
    from _canary.core.job import JobPhase
    from _canary.core.jobspec import Mask
    from _canary.session.workspace import Workspace

    upstream, dependent = make_dependent_pair(tmp_path)
    upstream.mask = Mask.masked(reason="not in this run")
    upstream.state.phase = JobPhase.RUNNING

    Workspace.refresh_masked_jobs([upstream, dependent])

    assert upstream.state.phase == JobPhase.RUNNING
    assert dependent.state.phase == JobPhase.PENDING
