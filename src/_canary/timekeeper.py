# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import time
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Generator


@dataclass
class Timekeeper:
    submitted: float = field(default=-1.0, init=False)
    started: float = field(default=-1.0, init=False)
    finished: float = field(default=-1.0, init=False)
    mark: float = field(default=-1.0, init=False, repr=False)

    def __serialize__(self) -> dict[str, Any]:
        return {
            "submitted": self.submitted,
            "started": self.started,
            "finished": self.finished,
            "mark": self.mark,
        }

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "Timekeeper":
        obj = cls()
        obj.submitted = float(d["submitted"])
        obj.started = float(d["started"])
        obj.finished = float(d["finished"])
        obj.mark = float(d["mark"])
        return obj

    def start(self) -> None:
        self.started = time.time()
        if self.submitted < 0:
            self.submitted = self.started

    def stop(self) -> None:
        self.finished = time.time()

    @contextmanager
    def timeit(self) -> Generator["Timekeeper", None, None]:
        try:
            self.start()
            yield self
        finally:
            self.stop()

    def queued(self) -> float:
        if self.started > 0:
            if self.submitted < 0:
                self.submitted = self.started
            return self.started - self.submitted
        return -1.0

    def duration(self) -> float:
        if self.started > 0 and self.finished > 0:
            return self.finished - self.started
        return -1.0

    def reset(self) -> None:
        self.submitted = -1.0
        self.started = -1.0
        self.finished = -1.0

    def update(self, *, started: float, finished: float, submitted: float = -1.0) -> None:
        self.submitted = submitted
        self.started = started
        self.finished = finished

    def isoformat(self, what: str) -> str:
        t: float = getattr(self, what)
        return datetime.datetime.fromtimestamp(t).isoformat(timespec="microseconds")

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "Timekeeper":
        self = cls()
        self.submitted = float(d["submitted"])
        self.started = float(d["started"])
        self.finished = float(d["finished"])
        return self

    @classmethod
    def from_isoformated_times(cls, d: dict[str, str]) -> "Timekeeper":
        self = cls()
        fn = datetime.datetime.fromisoformat
        self.submitted = fn(d["submitted"]).timestamp()
        self.started = fn(d["started"]).timestamp()
        self.finished = fn(d["finished"]).timestamp()
        return self


@dataclass
class PhaseTimer:
    """
    Named split timer.

    A split is a named interval.  For example:

        Queued:  submitted -> started
        Running: started -> finished

    The active phase can report live time.  Completed phases report fixed time.
    """

    stamp: float = -1.0
    current: str | None = None
    split_times: dict[str, float] = field(default_factory=dict)
    split_order: list[str] = field(default_factory=list)

    def __serialize__(self) -> dict[str, Any]:
        return {
            "stamp": self.stamp,
            "current": self.current,
            "split_times": self.split_times,
            "split_order": self.split_order,
        }

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "PhaseTimer":
        obj = cls()
        obj.stamp = d["stamp"]
        obj.current = d["current"]
        obj.split_times = d["split_times"]
        obj.split_order = d["split_order"]
        return obj

    def start(self, name: str, *, at: float | None = None) -> None:
        self.split_times.clear()
        self.split_order.clear()
        self.current = name
        self.stamp = time.time() if at is None else float(at)

    def transition(self, next_name: str, *, at: float | None = None) -> None:
        now = time.time() if at is None else float(at)

        if self.current is None or self.stamp < 0:
            self.start(next_name, at=now)
            return

        self._record(self.current, max(0.0, now - self.stamp))
        self.current = next_name
        self.stamp = now

    def stop(self, *, at: float | None = None) -> None:
        if self.current is None or self.stamp < 0:
            return

        now = time.time() if at is None else float(at)
        self._record(self.current, max(0.0, now - self.stamp))
        self.current = None
        self.stamp = now

    def _record(self, name: str, duration: float) -> None:
        if name not in self.split_times:
            self.split_order.append(name)
            self.split_times[name] = 0.0
        self.split_times[name] += duration

    def value(self, name: str, *, live: bool = True) -> float:
        value = self.split_times.get(name, -1.0)

        if live and self.current == name and self.stamp > 0:
            current_value = max(0.0, time.time() - self.stamp)
            if value < 0:
                return current_value
            return value + current_value

        return value

    def total(
        self, names: list[str] | tuple[str, ...] | None = None, *, live: bool = True
    ) -> float:
        if names is None:
            phase_names = list(self.split_order)
            if self.current is not None and self.current not in phase_names:
                phase_names.append(self.current)
        else:
            phase_names = list(names)
        total = 0.0
        found = False
        for name in phase_names:
            value = self.value(name, live=live)
            if value >= 0:
                total += value
                found = True
        return total if found else -1.0
