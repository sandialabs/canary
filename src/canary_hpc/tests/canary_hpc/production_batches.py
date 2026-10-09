# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Regression tests for batch wall limits against measured production batches.

``data/production_batches.json.gz`` records, for 29 batches of a production
regression suite run on single 48-cpu nodes, each job's declared timeout, cpu
count, exclusive flag and measured runtime, plus the measured elapsed time of
the whole batch.  The tests rebuild each batch as it would be estimated and
check that the wall limit canary would request is never shorter than the time
the batch actually took, while not being wildly over-provisioned.
"""

import gzip
import json
import math
from pathlib import Path
from typing import Any

import pytest

from canary_hpc import estimate
from canary_hpc.batchspec import BATCH_WALL_PENALTY
from canary_hpc.schedulepack import ScheduleTask
from canary_hpc.schedulepack import cheap_makespan
from canary_hpc.schedulepack import makespan_upper_bound

DATA = Path(__file__).parent / "data" / "production_batches.json.gz"


def load() -> dict[str, Any]:
    with gzip.open(DATA, "rt") as fh:
        return json.load(fh)


class RecordedJob:
    """A job whose estimate inputs come from the recorded production data."""

    def __init__(self, i: int, row: list[float], *, history: float | None) -> None:
        timeout, cpus, exclusive, runtime = row
        self.id = f"{i:064x}"
        self.timeout = float(timeout)
        self.cpus = int(cpus)
        self.exclusive = bool(exclusive)
        self.measured = float(runtime)
        self.history = history

    def total_timeout(self) -> float:
        return self.timeout

    def load_cached_runs(self) -> dict[str, Any] | None:
        if self.history is None:
            return None
        return {"metrics": {"time": {"mean": self.history, "max": self.history}}}


def wall_limit(jobs: list[RecordedJob], *, width: int) -> float:
    """Wall limit canary requests for ``jobs`` (mirrors batching + TestBatch.wall_limit)."""
    tasks = [
        ScheduleTask(
            id=job.id,
            width=width if job.exclusive else job.cpus,
            duration=float(math.ceil(estimate.estimate_runtime(job))),
        )
        for job in jobs
    ]
    return BATCH_WALL_PENALTY * makespan_upper_bound(tasks, width=width)


def batches(*, history_scale: float | None) -> list[tuple[float, list[RecordedJob]]]:
    """Return ``(measured elapsed, jobs)`` per batch.

    ``history_scale=None`` builds cold jobs (no timing history).  Otherwise each
    job's recorded history is its measured runtime times ``history_scale`` --
    a value below 1 models a history that is optimistic relative to this run.
    """
    data = load()
    out = []
    for batch in data["batches"]:
        jobs = []
        for i, row in enumerate(batch["jobs"]):
            history = None if history_scale is None else row[3] * history_scale
            jobs.append(RecordedJob(i, row, history=history))
        out.append((float(batch["elapsed"]), jobs))
    return out


def test_fixture_is_well_formed():
    data = load()
    assert data["width"] == 48
    assert len(data["batches"]) == 29
    assert sum(len(b["jobs"]) for b in data["batches"]) > 5000


def test_cheap_lower_bound_alone_is_optimistic():
    """Documents why the wall limit needs an upper bound: even with *perfect*
    per-job runtimes the packer's lower bound undershoots real batches."""
    data = load()
    width = data["width"]
    worst = 0.0
    for elapsed, jobs in batches(history_scale=1.0):
        tasks = [
            ScheduleTask(
                id=job.id, width=width if job.exclusive else job.cpus, duration=job.measured
            )
            for job in jobs
        ]
        worst = max(worst, elapsed / cheap_makespan(tasks, width=width))
    assert worst > 1.0


@pytest.mark.parametrize(
    "label,history_scale",
    [("cold", None), ("warm, accurate history", 1.0), ("warm, history 1.5x too fast", 1 / 1.5)],
)
def test_wall_limit_is_never_shorter_than_measured_elapsed(label, history_scale):
    width = load()["width"]
    for elapsed, jobs in batches(history_scale=history_scale):
        assert wall_limit(jobs, width=width) > elapsed, label


def test_cold_wall_limit_is_not_wildly_overprovisioned():
    """Cold walls are conservative, but nowhere near the old ~34x over-request."""
    width = load()["width"]
    requested = measured = 0.0
    for elapsed, jobs in batches(history_scale=None):
        requested += wall_limit(jobs, width=width)
        measured += elapsed
    assert requested / measured < 12.0


def test_warm_wall_limit_is_reasonably_tight():
    width = load()["width"]
    requested = measured = 0.0
    for elapsed, jobs in batches(history_scale=1.0):
        requested += wall_limit(jobs, width=width)
        measured += elapsed
    assert requested / measured < 4.0
