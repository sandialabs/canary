# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import datetime
import time
from contextlib import contextmanager
from typing import Generator


@dataclasses.dataclass
class Timekeeper:
    submitted: float = dataclasses.field(default=-1.0, init=False)
    started: float = dataclasses.field(default=-1.0, init=False)
    finished: float = dataclasses.field(default=-1.0, init=False)
    mark: float = dataclasses.field(default=-1.0, init=False, repr=False)

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
        if self.finished > 0:
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

    def asdict(self) -> dict[str, float]:
        return {"submitted": self.submitted, "started": self.started, "finished": self.finished}

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
