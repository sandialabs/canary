# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any
from typing import Callable
from typing import cast

from _canary.job import BaseJob
from _canary.job import JobState
from _canary.queue_executor import ExecutionSlot
from _canary.queue_executor import ResourceQueueExecutor
from _canary.status import Status
from _canary.timekeeper import Timekeeper


class DummyJob(BaseJob):
    def __init__(self, id: str = "j" * 64) -> None:
        self._id = id
        self.name = id[:7]
        self.state = JobState()
        self.timekeeper = Timekeeper()
        self._status = Status()
        self.saved = False
        self.refreshed = False

    @property
    def id(self) -> str:
        return self._id

    @property
    def status(self) -> Status:
        return self._status

    def cost(self) -> float:
        return 1.0

    def required_resources(self):
        return []

    def assign_resources(self, arg):
        self._resources = arg

    def free_resources(self):
        return getattr(self, "_resources", {})

    def refresh_readiness(self) -> None:
        return

    def is_runnable(self) -> bool:
        return True

    def is_ready(self) -> bool:
        return True

    def total_timeout(self) -> float:
        return 12.0

    def refresh(self) -> None:
        self.refreshed = True

    def save(self) -> None:
        self.saved = True

    def display_name(self, **kwargs: Any) -> str:
        return self.name

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(category=category, outcome=outcome, reason=reason, code=code)


class DummyQueue:
    def __init__(self) -> None:
        self.done_jobs: list[BaseJob] = []
        self.cleared: str | None = None

    def done(self, job: BaseJob) -> None:
        self.done_jobs.append(job)

    def clear(self, status: str) -> None:
        self.cleared = status

    def jobs(self) -> list[BaseJob]:
        return []

    def pending(self) -> list[BaseJob]:
        return []

    def status(self, start: float | None = None) -> str:
        return "dummy"


def make_executor(queue: DummyQueue) -> ResourceQueueExecutor:
    return ResourceQueueExecutor(cast(Any, queue), executor=lambda *a, **k: None, max_workers=1)


def add_listener(executor: ResourceQueueExecutor) -> list[tuple[str, ExecutionSlot]]:
    events: list[tuple[str, ExecutionSlot]] = []

    def listener(event: str, slot: ExecutionSlot) -> None:
        events.append((event, slot))

    executor.add_listener(cast(Callable[..., None], listener))
    return events


def test_handle_job_timeout_closes_slot_and_marks_timeout() -> None:
    queue = DummyQueue()
    executor = make_executor(queue)
    events = add_listener(executor)

    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    executor.slots_by_id[job.id] = slot
    executor.running[job.id] = slot
    executor.busy_workers[0] = job.id

    executor._handle_worker_payload({"job_id": job.id, "worker_id": 0, "event": "job_timeout"})

    assert job.state.is_done()
    assert job.status.outcome.name == "TIMEOUT"
    assert "timed out" in (job.status.reason or "")
    assert job.saved
    assert job.id in executor.finished
    assert job.id not in executor.running
    assert queue.done_jobs == [job]
    assert events[-1][0] == "job_finished"
    assert slot.timer.current is None
    assert slot.total_time(live=False) >= 0.0


def test_handle_job_died_with_signal_marks_error() -> None:
    queue = DummyQueue()
    executor = make_executor(queue)
    events = add_listener(executor)

    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    executor.slots_by_id[job.id] = slot
    executor.running[job.id] = slot
    executor.busy_workers[0] = job.id

    executor._handle_worker_payload(
        {"job_id": job.id, "worker_id": 0, "event": "job_died", "exitcode": -9}
    )

    assert job.state.is_done()
    assert job.status.outcome.name == "ERROR"
    assert "signal 9" in (job.status.reason or "")
    assert job.saved
    assert job.id in executor.finished
    assert job.id not in executor.running
    assert queue.done_jobs == [job]
    assert events[-1][0] == "job_finished"
    assert slot.timer.current is None


def test_handle_job_died_with_exitcode_marks_error() -> None:
    queue = DummyQueue()
    executor = make_executor(queue)

    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    executor.slots_by_id[job.id] = slot
    executor.submitted[job.id] = slot
    executor.busy_workers[0] = job.id

    executor._handle_worker_payload(
        {"job_id": job.id, "worker_id": 0, "event": "job_died", "exitcode": 17}
    )

    assert job.status.outcome.name == "ERROR"
    assert "exitcode 17" in (job.status.reason or "")
    assert job.id in executor.finished
    assert job.id not in executor.submitted
    assert queue.done_jobs == [job]


def test_terminate_all_marks_inflight_jobs_cancelled() -> None:
    import signal

    queue = DummyQueue()
    executor = make_executor(queue)
    events = add_listener(executor)

    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    executor.running[job.id] = slot

    # Avoid interacting with real worker processes.
    executor._shutdown_workers = lambda: None  # type: ignore[method-assign]

    executor._terminate_all(signal.SIGINT)

    assert job.state.is_done()
    assert job.status.outcome.name == "CANCELLED"
    assert job.id in executor.finished
    assert queue.done_jobs == [job]
    assert queue.cleared == "CANCELLED"
    assert events[-1][0] == "job_finished"
    assert slot.timer.current is None


def test_terminate_all_marks_inflight_jobs_error_for_non_interrupt() -> None:
    import signal

    queue = DummyQueue()
    executor = make_executor(queue)

    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    executor.submitted[job.id] = slot
    executor._shutdown_workers = lambda: None  # type: ignore[method-assign]

    executor._terminate_all(signal.SIGUSR2)

    assert job.state.is_done()
    assert job.status.outcome.name == "ERROR"
    assert job.id in executor.finished
    assert queue.done_jobs == [job]
    assert queue.cleared == "ERROR"
