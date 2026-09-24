# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any
from typing import Callable
from typing import cast

from _canary.core.status import Status
from _canary.core.timekeeper import Timekeeper
from _canary.job import BaseJob
from _canary.job import JobState
from _canary.queue_executor import ExecutionSlot
from _canary.queue_executor import ResourceQueueExecutor


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

    def clear(self, status: str = "CANCELLED", reason: str | None = None, code: int = -1) -> None:
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
    assert job.timekeeper._finished > 0
    assert job.timekeeper.total(live=False) >= 0.0


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
    assert job.timekeeper._finished > 0


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
    assert job.timekeeper._finished > 0


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
    # A Ctrl-C (SIGINT) is reported as INTERRUPTED (keyboard interrupt), not a
    # generic CANCELLED, so the results database and ``canary status`` reflect
    # that the user interrupted the run.
    assert job.status.outcome.name == "INTERRUPTED"
    assert "Keyboard interrupt" in (job.status.reason or "")
    assert job.id in executor.finished
    assert queue.done_jobs == [job]
    assert queue.cleared == "INTERRUPTED"
    assert events[-1][0] == "job_finished"
    assert job.timekeeper._finished > 0


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
    assert job.timekeeper._finished > 0


def test_resource_queue_clear_cancels_pending_jobs_terminally() -> None:
    """A pending job cleared on interrupt must become terminal, not NONE (NONE).

    Regression test: previously ``ResourceQueue.clear`` set the status but left
    ``state.phase == PENDING`` and never saved the job, so a job that was still
    queued when the run was interrupted surfaced as ``NONE (NONE)``.
    """
    import heapq
    import threading

    from _canary.queue import HeapSlot
    from _canary.queue import ResourceQueue

    class FakePool:
        def accommodates(self, req):
            return True

    jobs = [DummyJob(id=str(i) * 64) for i in range(3)]
    q = ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, FakePool()), jobs=None)
    for j in jobs:
        heapq.heappush(q._heap, HeapSlot(job=cast(BaseJob, j)))

    q.clear("INTERRUPTED", reason="Keyboard interrupt")

    assert len(q._heap) == 0
    for j in jobs:
        assert j.state.is_done()
        assert j.status.outcome.name == "INTERRUPTED"
        assert j.status.category.value == "ABORTED"
        assert "Keyboard interrupt" in (j.status.reason or "")
        assert j.saved


def test_resource_queue_clear_default_cancelled() -> None:
    """Non-interrupt clears use CANCELLED with a sensible default reason."""
    import heapq
    import threading

    from _canary.queue import HeapSlot
    from _canary.queue import ResourceQueue

    class FakePool:
        def accommodates(self, req):
            return True

    job = DummyJob(id="c" * 64)
    q = ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, FakePool()), jobs=None)
    heapq.heappush(q._heap, HeapSlot(job=cast(BaseJob, job)))

    q.clear("CANCELLED")

    assert job.state.is_done()
    assert job.status.outcome.name == "CANCELLED"
    assert job.status.category.value == "ABORTED"
    assert (job.status.reason or "") == "Cancelled before the job started"
    assert job.saved
