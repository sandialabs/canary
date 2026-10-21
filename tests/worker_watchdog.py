# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The worker watchdog must honor a job's declared worst-case lifetime."""

import multiprocessing
import time
from typing import Any
from typing import cast

from _canary.execution.queue_executor import _MainWorker


class _Job:
    id = "a" * 64

    def __init__(self, timeout: float, watchdog: float | None) -> None:
        self.timeout = timeout
        self._watchdog = watchdog

    def watchdog_timeout(self) -> float | None:
        return self._watchdog


def _sleeper(seconds: float) -> None:
    time.sleep(seconds)


def _monitor(job: _Job, seconds: float, monkeypatch) -> list[dict[str, Any]]:
    monkeypatch.setenv("CANARY_WORKER_WATCHDOG_GRACE", "0")
    monkeypatch.setenv("CANARY_KILL_GRACE", "0.2")
    sent: list[dict[str, Any]] = []
    worker = _MainWorker.__new__(_MainWorker)
    worker.worker_id = 0
    worker.poll_sleep = 0.01
    setattr(worker, "send", sent.append)
    ctx = multiprocessing.get_context("fork")
    setattr(worker, "local_q", ctx.Queue())
    worker._proc = ctx.Process(target=_sleeper, args=(seconds,))
    worker._proc.start()
    try:
        worker.monitor_job(cast(Any, job))
    finally:
        if worker._proc.is_alive():
            worker._proc.kill()
        worker._proc.join()
    return sent


def test_watchdog_uses_run_timeout_by_default(monkeypatch):
    sent = _monitor(_Job(timeout=0.5, watchdog=None), seconds=30, monkeypatch=monkeypatch)
    assert sent[-1]["event"] == "job_timeout"
    assert sent[-1]["timeout"] == 0.5


def test_watchdog_honors_declared_lifetime(monkeypatch):
    # e.g. an HPC batch waiting in the scheduler queue: its wall-clock "timeout"
    # is short, but the declared lifetime (queue + backstop) is longer.
    start = time.time()
    sent = _monitor(_Job(timeout=0.2, watchdog=2.0), seconds=1.0, monkeypatch=monkeypatch)
    assert time.time() - start >= 0.9
    assert sent[-1]["event"] == "job_died"  # the job exited on its own; no watchdog kill
