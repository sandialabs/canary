# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.rules import RerunRule
from _canary.rules import RuntimeRule
from _canary.rules import RuleOutcome
from _canary.select import RuntimeSelector
from _canary.testexec import ExecutionSpace


class RejectByName(RuntimeRule):
    def __init__(self, name: str, reason: str) -> None:
        super().__init__()
        self.name = name
        self.reason = reason

    @property
    def default_reason(self) -> str:
        return self.reason

    def __call__(self, job: Job) -> RuleOutcome:
        if job.name == self.name:
            return RuleOutcome.failed(self.reason)
        return RuleOutcome(True)


def make_job(tmp_path: Path, name: str) -> Job:
    spec = JobSpec(
        file_root=tmp_path,
        file_path=Path(f"{name}.pyt"),
        family=name,
        id=(name[0] * 64)[:64],
    )
    space = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path(name), session="s1")
    return Job(spec=spec, workspace=space)


def test_runtime_selector_preserves_first_mask_reason(tmp_path):
    a = make_job(tmp_path, "a")

    selector = RuntimeSelector([a], workspace=tmp_path)
    selector.add_rule(RejectByName("a", "first reason"))
    selector.add_rule(RejectByName("a", "second reason"))
    selector.run()

    assert a.mask
    assert a.mask.reason == "first reason"


def test_runtime_selector_rerun_rule_does_not_unmask_other_rule_failure(tmp_path):
    a = make_job(tmp_path, "a")
    a.status.set(outcome="FAILED")

    selector = RuntimeSelector([a], workspace=tmp_path)
    selector.add_rule(RerunRule("not_pass"))
    selector.add_rule(RejectByName("a", "resource unavailable"))
    selector.run()

    assert a.mask
    assert a.mask.reason == "resource unavailable"


def test_runtime_selector_non_rerun_rule_can_select_subset_after_rerun_all(tmp_path):
    a = make_job(tmp_path, "a")
    b = make_job(tmp_path, "b")

    selector = RuntimeSelector([a, b], workspace=tmp_path)
    selector.add_rule(RerunRule("all"))
    selector.add_rule(RejectByName("b", "filtered"))
    selector.run()

    assert not a.mask
    assert b.mask
    assert b.mask.reason == "filtered"
