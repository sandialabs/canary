# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.rules import RerunRule
from _canary.rules import RuleOutcome
from _canary.rules import RuntimeRule
from _canary.select import RuntimeSelector
from _canary.testexec import ExecutionSpace


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
