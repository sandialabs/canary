# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import datetime
import time
from contextlib import contextmanager
from typing import Any
from typing import Generator


@dataclasses.dataclass
class Timekeeper:
    started_on: str = dataclasses.field(default="NA", init=False)
    finished_on: str = dataclasses.field(default="NA", init=False)
    duration: float = dataclasses.field(default=-1.0, init=False)
    mark: float = dataclasses.field(default=-1.0, init=False, repr=False)

    def start(self) -> None:
        self.mark = time.monotonic()
        self.started_on = datetime.datetime.now().isoformat(timespec="microseconds")

    def stop(self) -> None:
        self.duration = time.monotonic() - self.mark
        self.finished_on = datetime.datetime.now().isoformat(timespec="microseconds")
        self.mark = -1.0

    @contextmanager
    def timeit(self) -> Generator["Timekeeper", None, None]:
        try:
            self.start()
            yield self
        finally:
            self.stop()

    def asdict(self) -> dict[str, Any]:
        return {
            "started_on": self.started_on,
            "finished_on": self.finished_on,
            "duration": self.duration,
        }
