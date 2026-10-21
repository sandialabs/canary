# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import _canary.api.status as status_api


@dataclass
class FakeCategory:
    value: str


@dataclass
class FakeOutcome:
    name: str


class FakeStatus:
    def __init__(
        self,
        *,
        category: str,
        outcome: str,
        code: int = 0,
        reason: str | None = None,
        success: bool = False,
        failure: bool = False,
        skipped: bool = False,
        diffed: bool = False,
        timeout: bool = False,
        cancelled: bool = False,
    ):
        self.category = FakeCategory(category)
        self.outcome = FakeOutcome(outcome)
        self.code = code
        self.reason = reason
        self._success = success
        self._failure = failure
        self._skipped = skipped
        self._diffed = diffed
        self._timeout = timeout
        self._cancelled = cancelled

    def is_success(self):
        return self._success

    def is_failure(self):
        return self._failure

    def is_skipped(self):
        return self._skipped

    def is_diffed(self):
        return self._diffed

    def is_timeout(self):
        return self._timeout

    def is_cancelled(self):
        return self._cancelled


class FakeState:
    def __init__(self, *, phase: str = "done", running: bool = False, done: bool = True):
        self.phase = SimpleNamespace(value=phase)
        self._running = running
        self._done = done

    def is_running(self):
        return self._running

    def is_done(self):
        return self._done


class FakeTimekeeper:
    def __init__(
        self,
        *,
        submitted: float = 10.0,
        staged: float = 11.0,
        started: float = 12.0,
        stopped: float = 17.5,
        finished: float = 18.0,
        duration: float | None = None,
    ):
        self._submitted = submitted
        self._staged = staged
        self._started = started
        self._stopped = stopped
        self._finished = finished
        self._duration = duration

    def duration(self):
        if self._duration is not None:
            return self._duration
        return self._stopped - self._started


def make_row(
    *,
    id: str,
    name: str,
    status: FakeStatus,
    state: FakeState | None = None,
    session: str = "session-1",
    timekeeper=None,
):
    return {
        "id": id,
        "spec_name": name,
        "spec_fullname": f"suite/{name}",
        "file_path": "suite/test.pyt",
        "session": session,
        "status": status,
        "state": state or FakeState(),
        "timekeeper": timekeeper
        if timekeeper is not None
        else {
            "_submitted": 10.0,
            "_staged": 11.0,
            "_started": 12.0,
            "_stopped": 17.5,
            "_finished": 18.0,
        },
    }


def patch_results(status_api, monkeypatch, rows):
    monkeypatch.setattr(status_api.app, "get_results", lambda: rows)


def test_jobs_returns_json_serializable_entries(monkeypatch):
    long_id = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    rows = {
        long_id: make_row(
            id=long_id,
            name="pass_test",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        )
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.jobs(full_ids=False)

    assert out == [
        {
            "id": "abcdef0",
            "full_id": long_id,
            "name": "pass_test",
            "fullname": "suite/pass_test",
            "file_path": "suite/test.pyt",
            "session": "session-1",
            "exit_code": 0,
            "phase": "done",
            "running": False,
            "done": True,
            "not_run": False,
            "passed": True,
            "failed": False,
            "skipped": False,
            "diffed": False,
            "timeout": False,
            "cancelled": False,
            "duration": 5.5,
            "status": {"category": "PASS", "outcome": "PASSED", "reason": None},
            "timings": {
                "pending": 1.0,
                "setup": 1.0,
                "running": 5.5,
                "teardown": 0.5,
                "total": 8.0,
            },
        }
    ]


def test_jobs_supports_timekeeper_object(monkeypatch):
    job_id = "a" * 64
    rows = {
        job_id: make_row(
            id=job_id,
            name="object_timekeeper",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
            timekeeper=FakeTimekeeper(duration=22.0),
        )
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.jobs()

    assert out[0]["duration"] == 22.0
    assert out[0]["timings"]["running"] == 5.5
    assert out[0]["timings"]["total"] == 8.0


def test_jobs_sorts_by_name_by_default(monkeypatch):
    rows = {
        "b": make_row(
            id="b" * 64,
            name="b_test",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "a": make_row(
            id="a" * 64,
            name="a_test",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [entry["name"] for entry in status_api.jobs()] == ["a_test", "b_test"]


def test_jobs_filters_by_category(monkeypatch):
    rows = {
        "pass": make_row(
            id="a" * 64,
            name="pass_test",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "fail": make_row(
            id="b" * 64,
            name="fail_test",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.jobs(category="fail")

    assert [entry["name"] for entry in out] == ["fail_test"]


def test_jobs_filters_by_outcome(monkeypatch):
    rows = {
        "timeout": make_row(
            id="a" * 64,
            name="timeout_test",
            status=FakeStatus(category="FAIL", outcome="TIMEOUT", timeout=True),
        ),
        "failed": make_row(
            id="b" * 64,
            name="failed_test",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.jobs(outcome="timeout")

    assert [entry["name"] for entry in out] == ["timeout_test"]


def test_jobs_filters_by_passed_failed_running_done_session_and_name(monkeypatch):
    rows = {
        "pass": make_row(
            id="a" * 64,
            name="thermal_pass",
            session="s1",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "fail": make_row(
            id="b" * 64,
            name="thermal_fail",
            session="s1",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
        ),
        "run": make_row(
            id="c" * 64,
            name="fluid_running",
            session="s2",
            status=FakeStatus(category="NONE", outcome="NONE"),
            state=FakeState(phase="running", running=True, done=False),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [e["name"] for e in status_api.jobs(passed=True)] == ["thermal_pass"]
    assert [e["name"] for e in status_api.jobs(passed=False)] == ["fluid_running", "thermal_fail"]
    assert [e["name"] for e in status_api.jobs(failed=True)] == ["thermal_fail"]
    assert [e["name"] for e in status_api.jobs(running=True)] == ["fluid_running"]
    assert [e["name"] for e in status_api.jobs(done=False)] == ["fluid_running"]
    assert [e["name"] for e in status_api.jobs(session="s1")] == ["thermal_fail", "thermal_pass"]
    assert [e["name"] for e in status_api.jobs(name_contains="fluid")] == ["fluid_running"]


def test_convenience_functions(monkeypatch):
    rows = {
        "pass": make_row(
            id="a" * 64,
            name="pass_test",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "fail": make_row(
            id="b" * 64,
            name="fail_test",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
        ),
        "run": make_row(
            id="c" * 64,
            name="running_test",
            status=FakeStatus(category="NONE", outcome="NONE"),
            state=FakeState(phase="running", running=True, done=False),
        ),
        "notrun": make_row(
            id="d" * 64,
            name="not_run_test",
            status=FakeStatus(category="NONE", outcome="NONE"),
            state=FakeState(phase="created", running=False, done=False),
        ),
        "skip": make_row(
            id="e" * 64,
            name="skipped_test",
            status=FakeStatus(category="SKIP", outcome="SKIPPED", skipped=True),
        ),
        "cancel": make_row(
            id="f" * 64,
            name="cancelled_test",
            status=FakeStatus(category="CANCEL", outcome="CANCELLED", cancelled=True),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [e["name"] for e in status_api.passed()] == ["pass_test"]
    assert [e["name"] for e in status_api.failed()] == ["fail_test"]
    assert [e["name"] for e in status_api.running()] == ["running_test"]
    assert [e["name"] for e in status_api.not_run()] == ["not_run_test"]
    assert [e["name"] for e in status_api.skipped()] == ["skipped_test"]
    assert [e["name"] for e in status_api.cancelled()] == ["cancelled_test"]

    assert [e["name"] for e in status_api.nonpassing()] == [
        "cancelled_test",
        "fail_test",
        "not_run_test",
        "running_test",
        "skipped_test",
    ]


def test_by_category_and_by_outcome(monkeypatch):
    rows = {
        "a": make_row(
            id="a" * 64,
            name="a",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "b": make_row(
            id="b" * 64,
            name="b",
            status=FakeStatus(category="FAIL", outcome="TIMEOUT", timeout=True),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [e["name"] for e in status_api.by_category("PASS")] == ["a"]
    assert [e["name"] for e in status_api.by_outcome("TIMEOUT")] == ["b"]


def test_summary_counts_status_classes(monkeypatch):
    rows = {
        "pass": make_row(
            id="a" * 64,
            name="passed",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "fail": make_row(
            id="b" * 64,
            name="failed",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
        ),
        "diff": make_row(
            id="c" * 64,
            name="diffed",
            status=FakeStatus(category="FAIL", outcome="DIFFED", diffed=True),
        ),
        "timeout": make_row(
            id="d" * 64,
            name="timeout",
            status=FakeStatus(category="FAIL", outcome="TIMEOUT", timeout=True),
        ),
        "skip": make_row(
            id="e" * 64,
            name="skipped",
            status=FakeStatus(category="SKIP", outcome="SKIPPED", skipped=True),
        ),
        "cancel": make_row(
            id="f" * 64,
            name="cancelled",
            status=FakeStatus(category="CANCEL", outcome="CANCELLED", cancelled=True),
        ),
        "running": make_row(
            id="g" * 64,
            name="running",
            status=FakeStatus(category="NONE", outcome="NONE"),
            state=FakeState(phase="running", running=True, done=False),
        ),
        "not_run": make_row(
            id="h" * 64,
            name="not_run",
            status=FakeStatus(category="NONE", outcome="NONE"),
            state=FakeState(phase="created", running=False, done=False),
        ),
        "other": make_row(
            id="i" * 64, name="other", status=FakeStatus(category="UNKNOWN", outcome="UNKNOWN")
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.summary()

    assert out["total"] == 9
    assert out["passed"] == 1
    assert out["failed"] == 1
    assert out["diffed"] == 1
    assert out["timeout"] == 1
    assert out["skipped"] == 1
    assert out["cancelled"] == 1
    assert out["running"] == 1
    assert out["not_run"] == 1
    assert out["other"] == 1
    assert out["nonpassing"] == 8
    assert out["ok"] is False


def test_summary_ok_when_all_jobs_pass(monkeypatch):
    rows = {
        "a": make_row(
            id="a" * 64,
            name="a",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "b": make_row(
            id="b" * 64,
            name="b",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert status_api.summary()["ok"] is True
    assert status_api.ok() is True


def test_summary_not_ok_for_empty_workspace(monkeypatch):
    patch_results(status_api, monkeypatch, {})

    assert status_api.summary()["ok"] is False
    assert status_api.ok() is False


def test_snapshot_includes_useful_subsets(monkeypatch):
    rows = {
        "pass": make_row(
            id="a" * 64,
            name="pass_test",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        ),
        "fail": make_row(
            id="b" * 64,
            name="fail_test",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
        ),
        "run": make_row(
            id="c" * 64,
            name="running_test",
            status=FakeStatus(category="NONE", outcome="NONE"),
            state=FakeState(phase="running", running=True, done=False),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.snapshot(full_ids=False)

    assert out["ok"] is False
    assert out["summary"]["total"] == 3
    assert [e["name"] for e in out["jobs"]] == ["fail_test", "pass_test", "running_test"]
    assert [e["name"] for e in out["failed"]] == ["fail_test"]
    assert [e["name"] for e in out["running"]] == ["running_test"]
    assert [e["name"] for e in out["not_run"]] == []
    assert [e["name"] for e in out["nonpassing"]] == ["fail_test", "running_test"]
    assert out["jobs"][0]["id"] == "bbbbbbb"
    assert out["jobs"][0]["full_id"] == "b" * 64


def test_snapshot_can_omit_jobs(monkeypatch):
    rows = {
        "a": make_row(
            id="a" * 64,
            name="a",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
        )
    }
    patch_results(status_api, monkeypatch, rows)

    out = status_api.snapshot(include_jobs=False)

    assert out == {
        "ok": True,
        "summary": {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "diffed": 0,
            "timeout": 0,
            "skipped": 0,
            "cancelled": 0,
            "running": 0,
            "not_run": 0,
            "nonpassing": 0,
            "other": 0,
            "ok": True,
        },
    }


def test_slowest_returns_jobs_by_duration_descending(monkeypatch):
    rows = {
        "fast": make_row(
            id="a" * 64,
            name="fast",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
            timekeeper=FakeTimekeeper(duration=1.0),
        ),
        "slow": make_row(
            id="b" * 64,
            name="slow",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
            timekeeper=FakeTimekeeper(duration=10.0),
        ),
        "medium": make_row(
            id="c" * 64,
            name="medium",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
            timekeeper=FakeTimekeeper(duration=5.0),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [e["name"] for e in status_api.slowest(n=2)] == ["slow", "medium"]
    assert [e["name"] for e in status_api.slowest(n=-1)] == ["slow", "medium", "fast"]


def test_slowest_omits_unavailable_durations_by_default(monkeypatch):
    rows = {
        "missing": make_row(
            id="a" * 64,
            name="missing",
            status=FakeStatus(category="NONE", outcome="NONE"),
            timekeeper={
                "_submitted": -1,
                "_staged": -1,
                "_started": -1,
                "_stopped": -1,
                "_finished": -1,
            },
        ),
        "done": make_row(
            id="b" * 64,
            name="done",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
            timekeeper=FakeTimekeeper(duration=3.0),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [e["name"] for e in status_api.slowest(n=-1)] == ["done"]
    assert [e["name"] for e in status_api.slowest(n=-1, include_incomplete=True)] == [
        "done",
        "missing",
    ]


def test_sort_by_duration_status_and_session(monkeypatch):
    rows = {
        "a": make_row(
            id="a" * 64,
            name="a",
            session="s2",
            status=FakeStatus(category="FAIL", outcome="FAILED", failure=True),
            timekeeper=FakeTimekeeper(duration=9.0),
        ),
        "b": make_row(
            id="b" * 64,
            name="b",
            session="s1",
            status=FakeStatus(category="PASS", outcome="PASSED", success=True),
            timekeeper=FakeTimekeeper(duration=1.0),
        ),
    }
    patch_results(status_api, monkeypatch, rows)

    assert [e["name"] for e in status_api.jobs(sort_by="duration")] == ["b", "a"]
    assert [e["name"] for e in status_api.jobs(sort_by="duration", reverse=True)] == ["a", "b"]
    assert [e["name"] for e in status_api.jobs(sort_by="session")] == ["b", "a"]
    assert [e["name"] for e in status_api.jobs(sort_by="status")] == ["a", "b"]


def test_invalid_sort_key_raises(monkeypatch):
    patch_results(status_api, monkeypatch, {})

    with pytest.raises(ValueError, match="invalid sort key"):
        status_api.jobs(sort_by="bogus")


def test_raw_results_returns_application_results(monkeypatch):
    raw = {"abc": {"some": "row"}}
    patch_results(status_api, monkeypatch, raw)

    assert status_api.raw_results() is raw
