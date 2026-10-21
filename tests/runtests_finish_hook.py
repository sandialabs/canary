# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the ``canary_runtests_finish`` session hook."""

from types import SimpleNamespace

import pytest

import canary
from _canary.execution.runtest import Runner
from _canary.execution.runtest import canary_runtests
from _canary.plugins import hookspec


def _runner() -> Runner:
    return Runner(jobs=[], session="s", workspace=SimpleNamespace())  # type: ignore[arg-type]


class _Recorder:
    def __init__(self, fail_runtests: bool = False, fail_finish: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_runtests = fail_runtests
        self.fail_finish = fail_finish

    @canary.hookimpl
    def canary_runtests_start(self, runner):
        self.calls.append("start")

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner):
        self.calls.append("runtests")
        if self.fail_runtests:
            raise RuntimeError("runtests failed")
        return True

    @canary.hookimpl
    def canary_runtests_finish(self, runner):
        self.calls.append("finish")
        if self.fail_finish:
            raise RuntimeError("finish failed")

    @canary.hookimpl(tryfirst=True)
    def canary_runtests_report(self, runner):
        self.calls.append("report")


@pytest.fixture
def recorder_factory():
    registered: list[_Recorder] = []

    def make(**kwargs) -> _Recorder:
        rec = _Recorder(**kwargs)
        canary.config.pluginmanager.register(rec, name=f"recorder{len(registered)}")
        registered.append(rec)
        return rec

    yield make
    for rec in registered:
        canary.config.pluginmanager.unregister(rec)


def test_hookspec_is_additive():
    impl = getattr(hookspec.canary_runtests_finish, "canary_spec")
    assert impl["firstresult"] is False


def test_finish_runs_between_runtests_and_report(recorder_factory):
    rec = recorder_factory()
    canary_runtests(_runner())
    assert rec.calls == ["start", "runtests", "finish", "report"]


def test_finish_runs_when_runtests_raises(recorder_factory):
    rec = recorder_factory(fail_runtests=True)
    with pytest.raises(RuntimeError, match="runtests failed"):
        canary_runtests(_runner())
    assert rec.calls == ["start", "runtests", "finish", "report"]


def test_finish_exception_does_not_block_report(recorder_factory):
    rec = recorder_factory(fail_finish=True)
    canary_runtests(_runner())
    assert rec.calls == ["start", "runtests", "finish", "report"]
