# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the TUI live-run progress tracker (``_canary.tui.progress``).

RunProgress is fed job-lifecycle events (from the event bus, off the publisher
thread) and produces an immutable snapshot for the renderer.  These tests pin
the tally arithmetic, the qsize-derived total, terminal-vs-start bookkeeping,
and the active/inactive gating.
"""

from _canary.events import Event
from _canary.tui.progress import RunProgress


def _job(job_id, *, qsize=-1, status=""):
    return Event(
        name="",  # overwritten by caller via _ev
        payload={"job": {"id": job_id, "qsize": qsize, "status": status}},
    )


def _ev(name, job_id, *, qsize=-1, status=""):
    return Event(name=name, payload={"job": {"id": job_id, "qsize": qsize, "status": status}})


def test_progress_counts_running_and_finished():
    p = RunProgress()
    p.begin(total=3)
    p.on_event(_ev("job_started", "a", qsize=3))
    p.on_event(_ev("job_started", "b", qsize=3))
    s = p.snapshot()
    assert s.total == 3
    assert s.running == 2
    assert s.finished == 0
    assert s.pending == 1

    p.on_event(_ev("job_finished", "a", qsize=3, status="PASS"))
    s = p.snapshot()
    assert s.running == 1
    assert s.finished == 1
    assert s.by_status == {"PASS": 1}
    assert 0.0 < s.fraction < 1.0


def test_progress_learns_total_from_qsize_when_unknown():
    p = RunProgress()
    p.begin(total=0)  # caller does not know the count
    p.on_event(_ev("job_started", "a", qsize=5))
    assert p.snapshot().total == 5


def test_progress_terminal_events_are_idempotent():
    """A duplicate terminal event must not double-count a job."""
    p = RunProgress()
    p.begin(total=1)
    p.on_event(_ev("job_started", "a", qsize=1))
    p.on_event(_ev("job_finished", "a", qsize=1, status="FAIL"))
    p.on_event(_ev("job_finished", "a", qsize=1, status="FAIL"))
    s = p.snapshot()
    assert s.finished == 1
    assert s.by_status == {"FAIL": 1}


def test_progress_timeout_and_died_count_as_finished():
    p = RunProgress()
    p.begin(total=2)
    p.on_event(_ev("job_started", "a", qsize=2))
    p.on_event(_ev("job_started", "b", qsize=2))
    p.on_event(_ev("job_timeout", "a", qsize=2, status="TIMEOUT"))
    p.on_event(_ev("job_died", "b", qsize=2, status="FAIL"))
    s = p.snapshot()
    assert s.finished == 2
    assert s.running == 0
    assert s.fraction == 1.0


def test_progress_ignores_events_when_inactive():
    p = RunProgress()
    # No begin() -> inactive; events are dropped.
    p.on_event(_ev("job_started", "a", qsize=3))
    s = p.snapshot()
    assert s.active is False
    assert s.finished == 0 and s.running == 0

    p.begin(total=1)
    p.on_event(_ev("job_finished", "a", qsize=1, status="PASS"))
    p.end()
    # After end(), snapshot reports inactive but retains no running work.
    assert p.snapshot().active is False


def test_progress_tolerates_missing_payload():
    p = RunProgress()
    p.begin(total=1)
    # Malformed events must not raise on the publisher-thread hot path.
    p.on_event(Event("job_started", {}))
    p.on_event(Event("job_finished", {"job": {}}))
    assert p.snapshot().finished == 0


def test_running_jobs_reports_in_flight_payloads():
    """running_jobs() returns the payloads of started-but-not-finished jobs."""
    p = RunProgress()
    p.begin(total=3)
    p.on_event(_ev("job_started", "a", qsize=3, status="RUNNING"))
    p.on_event(_ev("job_started", "b", qsize=3, status="RUNNING"))
    p.on_event(_ev("job_started", "c", qsize=3, status="RUNNING"))
    p.on_event(_ev("job_finished", "b", qsize=3, status="PASS"))
    running = {j["id"] for j in p.running_jobs()}
    assert running == {"a", "c"}  # b finished, so it drops out
    # The returned dicts are copies -- mutating them must not corrupt state.
    p.running_jobs()[0]["id"] = "mutated"
    assert {j["id"] for j in p.running_jobs()} == {"a", "c"}


def test_running_jobs_cleared_on_begin():
    p = RunProgress()
    p.begin(total=1)
    p.on_event(_ev("job_started", "a", qsize=1))
    assert p.running_jobs()
    p.begin(total=1)  # a fresh run resets the in-flight set
    assert p.running_jobs() == []
