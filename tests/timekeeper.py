import time

import pytest

from _canary.timekeeper import Timekeeper


def test_defaults():
    tk = Timekeeper()
    assert tk.submitted == -1.0
    assert tk.started == -1.0
    assert tk.finished == -1.0
    assert tk.queued() == -1.0
    assert tk.duration() == -1.0


def test_start_sets_started_and_submitted_if_unset(monkeypatch):
    tk = Timekeeper()

    monkeypatch.setattr(time, "time", lambda: 123.0)
    tk.start()

    assert tk.started == 123.0
    assert tk.submitted == 123.0


def test_start_does_not_override_submitted(monkeypatch):
    tk = Timekeeper()
    tk.submitted = 1.5

    monkeypatch.setattr(time, "time", lambda: 10.0)
    tk.start()

    assert tk.started == 10.0
    assert tk.submitted == 1.5


def test_stop_sets_finished(monkeypatch):
    tk = Timekeeper()
    tk.started = 5.0

    monkeypatch.setattr(time, "time", lambda: 12.0)
    tk.stop()

    assert tk.finished == 12.0
    assert tk.duration() == pytest.approx(7.0)


def test_timeit_context_manager(monkeypatch):
    tk = Timekeeper()
    times = iter([100.0, 105.0])
    monkeypatch.setattr(time, "time", lambda: next(times))

    with tk.timeit():
        assert tk.started == 100.0
        assert tk.submitted == 100.0
        assert tk.finished == -1.0

    assert tk.finished == 105.0
    assert tk.duration() == pytest.approx(5.0)
    assert tk.queued() == pytest.approx(0.0)


def test_queued_sets_submitted_if_missing_and_started_set():
    tk = Timekeeper()
    tk.started = 10.0
    tk.submitted = -1.0

    q = tk.queued()
    assert tk.submitted == 10.0
    assert q == pytest.approx(0.0)


def test_update_sets_fields():
    tk = Timekeeper()
    tk.update(submitted=1.0, started=2.0, finished=5.0)
    assert tk.submitted == 1.0
    assert tk.started == 2.0
    assert tk.finished == 5.0
    assert tk.queued() == pytest.approx(1.0)
    assert tk.duration() == pytest.approx(3.0)


def test_reset_resets_fields_but_not_mark():
    tk = Timekeeper()
    tk.submitted = 1.0
    tk.started = 2.0
