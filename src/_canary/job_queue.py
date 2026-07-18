import abc
import dataclasses
import time
from typing import Any
from typing import Callable
from typing import Literal

from .job import BaseJob
from .util import logging

logger = logging.get_logger(__name__)


EventTypes = Literal["job_submitted", "job_started", "job_finished"]


@dataclasses.dataclass
class ExecutionSlot:
    job: BaseJob
    qrank: int
    qsize: int
    spawned: float
    worker_id: int
    submitted: float = -1.0
    started: float = -1.0
    finished: float = -1.0

    def queued(self) -> float:
        if self.started < 0:
            return time.time() - self.spawned
        return self.started - self.spawned

    def elapsed(self) -> float:
        if self.finished < 0:
            return time.time() - self.spawned
        return self.finished - self.spawned

    def running(self) -> float:
        if self.started < 0:
            return -1.0
        if self.finished >= 0:
            return self.finished - self.started
        return time.time() - self.started


class JobQueue(abc.ABC):
    def __init__(self) -> None:
        self.listeners: list[Callable[..., None]] = []
        self.started_on: float = -1
        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}
        self.slots_by_id: dict[str, ExecutionSlot] = {}

    @abc.abstractmethod
    def __len__(self) -> int: ...

    @abc.abstractmethod
    def _get_job(self) -> BaseJob: ...

    def get(self, qrank: int = -1, worker_id: int = -1) -> ExecutionSlot:
        job = self._get_job()
        slot = ExecutionSlot(
            job=job, spawned=time.time(), qrank=qrank, qsize=len(self), worker_id=worker_id
        )
        self.slots_by_id[job.id] = slot
        self.submitted[job.id] = slot
        return slot

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    @abc.abstractmethod
    def jobs(self) -> list[BaseJob]: ...

    @abc.abstractmethod
    def pending(self) -> list[BaseJob]: ...

    @abc.abstractmethod
    def status(self, start: float | None = None) -> str: ...

    def add_listener(self, callback: Callable[..., None]) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[..., None]) -> None:
        try:
            self.listeners.remove(callback)
        except ValueError:  # nosec B110
            pass

    def notify_listeners(self, event: EventTypes, slot: ExecutionSlot):
        for cb in self.listeners:
            cb(event, slot)

    def update(self, payload: dict[str, Any]) -> None:
        job_id: str = payload["job_id"]
        event: str = payload["event"] or ""

        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return

        match event:
            case "job_submitted":
                slot.job.on_submitted()
                slot.job.timekeeper.submitted = slot.submitted = float(
                    payload.get("timestamp", time.time())
                )
                self.notify_listeners(event, slot)

            case "job_started":
                slot.job.timekeeper.started = slot.started = float(
                    payload.get("timestamp", time.time())
                )
                slot.job.on_started()
                self.running[job_id] = slot
                self.submitted.pop(job_id, None)
                self.notify_listeners(event, slot)

            case "job_updated":
                # This job, running in a different process, is passing updated attributes
                attrs = payload.get("attrs", {})
                if not isinstance(attrs, dict):
                    logger.warning(f"Malformed job_updated payload: {payload!r}")
                    return
                for name, value in attrs.items():
                    if isinstance(name, str) and not name.startswith("_"):
                        setattr(slot.job, name, value)

            case "job_finished":
                # job_started event sent by worker process
                slot.job.timekeeper.finished = slot.finished = time.time()
                try:
                    slot.job.refresh()
                except Exception:
                    logger.exception(f"Post-processing failed for job {slot.job}")
                    slot.job.set_status(outcome="ERROR", reason="Post-processing failure")
                    try:
                        slot.job.save()
                    except Exception as e:
                        logger.debug("job.save failed: %s", e)
                finally:
                    slot.job.on_finished()
                    self.finished[job_id] = slot
                    self.running.pop(job_id, None)
                    self.submitted.pop(job_id, None)
                    self.notify_listeners(event, slot)

            case "job_timeout":
                if slot.submitted < 0.0:
                    slot.submitted = time.time()
                if slot.started < 0.0:
                    slot.started = time.time()
                slot.finished = time.time()
                reason: str
                t = slot.job.total_timeout()
                reason = f"Job timed out after {t} s."
                try:
                    slot.job.refresh()
                except Exception as e:
                    logger.debug("job.refresh failed during job_timeout: %s", e)
                slot.job.on_finished()
                slot.job.set_status(outcome="TIMEOUT", reason=reason)
                slot.job.timekeeper.submitted = slot.submitted
                slot.job.timekeeper.started = slot.started
                slot.job.timekeeper.finished = slot.finished
                slot.job.save()

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.notify_listeners("job_finished", slot)

            case "job_died":
                slot.finished = time.time()
                try:
                    slot.job.refresh()
                except Exception as e:
                    logger.debug("job.refresh failed during job_died: %s", e)
                exitcode = payload.get("exitcode", None)
                reason = "Worker job process died unexpectedly"
                if isinstance(exitcode, int):
                    if exitcode < 0:
                        reason += f" (signal {-exitcode})"
                    else:
                        reason += f" (exitcode {exitcode})"

                slot.job.on_finished()
                slot.job.set_status(outcome="ERROR", reason=reason)
                slot.job.timekeeper.submitted = slot.submitted
                slot.job.timekeeper.started = slot.started
                slot.job.timekeeper.finished = slot.finished
                slot.job.save()

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.notify_listeners("job_finished", slot)

            case _:
                logger.warning(f"Unexpected worker payload for {job_id[:7]}: {payload}")
