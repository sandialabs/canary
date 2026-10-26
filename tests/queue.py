# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import threading
from typing import Any
from typing import cast

from _canary.core.job import BaseJob
from _canary.core.job import JobState
from _canary.core.status import Status
from _canary.core.timekeeper import Timekeeper
from _canary.execution.queue import ResourceQueue


class DummyJob(BaseJob):
    def __init__(self, id: str = "j" * 64) -> None:
        self._id = id
        self.name = id[:7]
        self.state = JobState()
        self.timekeeper = Timekeeper()
        self._status = Status()
        self.saved = False
        self._resources: dict[str, Any] = {"cpus": [{"id": "0", "slots": 1, "node": "n0"}]}

    @property
    def id(self) -> str:
        return self._id

    @property
    def status(self) -> Status:
        return self._status

    def required_resources(self):
        return []

    def assign_resources(self, arg):
        self._resources = arg

    def free_resources(self):
        return self._resources

    def refresh_readiness(self) -> None:
        return None

    def is_runnable(self) -> bool:
        return True

    def is_ready(self) -> bool:
        return True

    @property
    def timeout(self) -> float:
        return 12.0

    def refresh(self) -> None:
        return None

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


class FakePool:
    def __init__(self, *, fail_checkin: bool = False) -> None:
        self.fail_checkin = fail_checkin
        self.checked_in: list[dict[str, Any]] = []

    def accommodates(self, req):
        return True

    def checkin(self, resources: dict[str, Any]) -> None:
        if self.fail_checkin:
            raise RuntimeError("boom")
        self.checked_in.append(resources)


def test_done_on_nonbusy_job_does_not_crash() -> None:
    q = ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, FakePool()), jobs=None)
    job = DummyJob(id="x" * 64)

    q.done(cast(BaseJob, job))

    assert q._busy == {}
    assert q._finished == {}


def test_done_checkin_failure_leaves_job_busy() -> None:
    pool = FakePool(fail_checkin=True)
    q = ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, pool), jobs=None)
    job = DummyJob(id="y" * 64)
    q._busy[job.id] = job

    q.done(cast(BaseJob, job))

    assert job.id in q._busy
    assert job.id not in q._finished
    assert pool.checked_in == []
