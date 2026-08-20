# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import time
from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass
class Timekeeper:
    """
    Track the lifecycle timestamps for a job.

    The canonical lifecycle is:

        submitted -> staged -> started -> stopped -> returned

    The corresponding reporting phases are:

        Pending   = staged   - submitted
        Setup     = started  - staged
        Running   = stopped  - started
        Teardown  = returned - stopped
        Elapsed   = now      - submitted

    """

    _submitted: float = field(default=-1.0, init=False)
    _staged: float = field(default=-1.0, init=False)
    _started: float = field(default=-1.0, init=False)
    _stopped: float = field(default=-1.0, init=False)
    _finished: float = field(default=-1.0, init=False)

    def __serialize__(self) -> dict[str, Any]:
        return dict(vars(self))

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "Timekeeper":
        obj = cls()
        for var, val in d.items():
            setattr(obj, var, val)
        return obj

    def open(self, at: float | None = None) -> None:
        self.reset()
        self._submitted = time.time() if at is None else float(at)

    def maybe_open(self, at: float | None = None) -> None:
        if self._submitted < 0:
            self.open(at=at)

    def stage(self, at: float | None = None) -> None:
        self._staged = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._staged

    def maybe_stage(self, at: float | None = None) -> None:
        if self._staged < 0:
            self.stage(at=at)

    def start(self, at: float | None = None) -> None:
        self._started = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._started
        if self._staged < 0:
            self._staged = self._submitted

    def maybe_start(self, at: float | None = None) -> None:
        if self._started < 0:
            self.start(at=at)

    def stop(self, at: float | None = None) -> None:
        self._stopped = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._stopped
        if self._staged < 0:
            self._staged = self._stopped
        if self._started < 0:
            self._started = self._stopped

    def maybe_stop(self, at: float | None = None) -> None:
        if self._stopped < 0:
            self.stop(at=at)

    def close(self, at: float | None = None) -> None:
        self._finished = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._finished
        if self._staged < 0:
            self._staged = self._finished
        if self._started < 0:
            self._started = self._finished
        if self._stopped < 0:
            self._stopped = self._finished

    def maybe_close(self, at: float | None = None) -> None:
        if self._finished < 0:
            self.close(at=at)

    finish = close

    def pending(self, *, live: bool = False) -> float:
        return delta(self._submitted, self._staged, live=live)

    def staging(self, *, live: bool = False) -> float:
        return delta(self._staged, self._started, live=live)

    def running(self, *, live: bool = False) -> float:
        return delta(self._started, self._stopped, live=live)

    duration = running

    def finishing(self, *, live: bool = False) -> float:
        return delta(self._stopped, self._finished, live=live)

    def total(self, *, live: bool = False) -> float:
        return delta(self._submitted, self._finished, live=live)

    def elapsed(self, *, live: bool = False) -> float:
        return self.total(live=live)

    def reset(self) -> None:
        for var in vars(self):
            setattr(self, var, -1.0)

    def update(self, **kwargs: float) -> None:
        # ``submitted`` and ``launched`` are accepted for backward compatibility.
        for key, val in kwargs.items():
            setattr(self, key, float(val))

    def sync(self, other: "Timekeeper") -> None:
        for var, value in vars(other).items():
            setattr(self, var, float(value))


def delta(start: float, stop: float, *, live: bool = False) -> float:
    if start <= 0:
        return -1.0
    if stop > 0:
        return stop - start
    if live:
        return time.time() - start
    return -1.0
