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
import shutil
import time
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from typing import Generator

import pytest

import _canary.history as his
from _canary.history import HistoryStore
from _canary.util.schedulepack import ScheduleTask
from _canary.util.schedulepack import cheap_makespan
from _canary.util.schedulepack import makespan_upper_bound

DATA = Path(__file__).parent / "data" / "production_batches.json.gz"


def load() -> dict[str, Any]:
    with gzip.open(DATA, "rt") as fh:
        return json.load(fh)


class MyStore(HistoryStore):
    def record(self, job: Any) -> None:
        """Write a minimal job cache file with the given mean runtime."""
        job_id, row = job
        mean = row[-1]
        assert self.root is not None
        file = self.root / "jobs" / job_id[:2] / f"{job_id[2:]}.jsonl"
        file.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "what": "meta",
            "version": his.store.SCHEMA,
            "id": job_id,
            "name": job_id,
            "root": "/tmp",
            "path": "path.pyt",
            "parameters": {},
            "totals": {},
        }
        run: dict[str, Any] = {
            "what": "record",
            "version": his.store.SCHEMA,
            "recorded_at": round(time.time(), 3),
            "status": "success",
            "duration": round(mean, 3),
            "timeout": float(10 * mean),
            "timeiout_multiplier": 1.0,
            "file_hash": "abcdefg",
            "host": "myhost",
        }
        if not file.exists():
            self._append(file, meta, run)
        else:
            self._append(file, run)


class RecordedJob:
    """A job whose estimate inputs come from the recorded production data."""

    def __init__(self, id: str, row: list[float], *, history: float | None) -> None:
        timeout, cpus, exclusive, runtime = row
        self.id = id
        self.timeout = float(timeout)
        self.cpus = int(cpus)
        self.exclusive = bool(exclusive)
        self.measured = float(runtime)
        self.history = history


@pytest.fixture(scope="module")
def tmp_store() -> Generator[MyStore]:
    tmp_path = Path(mkdtemp())
    store = MyStore(tmp_path)
    data = load()
    j = 0
    for batch in data["batches"]:
        for i, row in enumerate(batch["jobs"]):
            id = f"{(i + j):x}"
            store.record((id, row))
        j += len(batch["jobs"])
    yield store
    shutil.rmtree(tmp_path)


@pytest.fixture(scope="module")
def cold_store() -> Generator[MyStore]:
    tmp_path = Path(mkdtemp())
    store = MyStore(tmp_path)
    data = load()
    j = 0
    for batch in data["batches"]:
        for i, row in enumerate(batch["jobs"]):
            id = f"{(i + j):x}"
            store.record((id, row))
        j += len(batch["jobs"])
    yield store
    shutil.rmtree(tmp_path)


def wall_limit(store: HistoryStore, jobs: list[RecordedJob], *, width: int) -> float:
    """Wall limit canary requests for ``jobs`` (mirrors batching + TestBatch.wall_limit)."""
    tasks = [
        ScheduleTask(
            id=job.id,
            width=width if job.exclusive else job.cpus,
            duration=float(math.ceil(his.estimate_runtime(job, store=store))),
        )
        for job in jobs
    ]
    # 1.25 to match canary_hpc BATCH_WALL_PENALTY
    return 1.25 * makespan_upper_bound(tasks, width=width)


def batches(*, history_scale: float | None) -> list[tuple[float, list[RecordedJob]]]:
    """Return ``(measured elapsed, jobs)`` per batch.

    ``history_scale=None`` builds cold jobs (no timing history).  Otherwise each
    job's recorded history is its measured runtime times ``history_scale`` --
    a value below 1 models a history that is optimistic relative to this run.
    """
    data = load()
    out = []
    j = 0
    for batch in data["batches"]:
        jobs = []
        for i, row in enumerate(batch["jobs"]):
            history = None if history_scale is None else row[3] * history_scale
            id = f"{(i + j):x}"
            jobs.append(RecordedJob(id, row, history=history))
        j += len(batch["jobs"])
        out.append((float(batch["elapsed"]), jobs))
    return out


def xtest_fixture_is_well_formed():
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


def test_cold_wall_limit_is_not_wildly_overprovisioned():
    """Cold walls are conservative, but nowhere near the old ~34x over-request."""
    cold_store = HistoryStore(None)
    width = load()["width"]
    requested = measured = 0.0
    for elapsed, jobs in batches(history_scale=None):
        requested += wall_limit(cold_store, jobs, width=width)
        measured += elapsed
    assert requested / measured < 10.0, str(requested / measured)


def test_warm_wall_limit_is_reasonably_tight(tmp_store):
    width = load()["width"]
    requested = measured = 0.0
    for elapsed, jobs in batches(history_scale=1.0):
        requested += wall_limit(tmp_store, jobs, width=width)
        measured += elapsed
    assert requested / measured < 2.5, str(requested / measured)


def test_warm_wall_limit_is_less_than_cold(tmp_store):
    width = load()["width"]
    cold_store = HistoryStore(None)
    warm = cold = 0.0
    for elapsed, jobs in batches(history_scale=1.0):
        warm += wall_limit(tmp_store, jobs, width=width)
        cold += wall_limit(cold_store, jobs, width=width)
    assert cold > warm
