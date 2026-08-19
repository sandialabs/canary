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

        opened -> launched -> started -> finished -> closed

    The corresponding reporting phases are:

        Queued   = launched - opened
        Startup  = started  - launched
        Running  = finished - started
        Teardown = closed   - finished
        Elapsed  = closed   - opened

    Meanings:

    - opened:
        Parent opened/submitted the job to an execution backend.

    - launched:
        The backend launched the child-side execution process
        (for example, ``canary flux exec`` or ``canary hpc exec``).

    - started:
        The actual Canary job/test execution started in the child.

    - finished:
        The actual Canary job/test execution finished in the child.

    - closed:
        The child-side execution process returned control to the parent.

    For local/non-HPC execution, missing intermediate timestamps are filled so
    existing semantics remain useful:

        launched defaults to started
        closed defaults to finished
    """

    opened: float = field(default=-1.0, init=False)
    launched: float = field(default=-1.0, init=False)
    started: float = field(default=-1.0, init=False)
    finished: float = field(default=-1.0, init=False)
    closed: float = field(default=-1.0, init=False)

    def __serialize__(self) -> dict[str, Any]:
        return {
            "opened": self.opened,
            "launched": self.launched,
            "started": self.started,
            "finished": self.finished,
            "closed": self.closed,
        }

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "Timekeeper":
        obj = cls()

        # Backward compatibility with older serialized Timekeeper objects.
        old_submitted = float(d.get("submitted", -1.0))
        old_started = float(d.get("started", -1.0))
        old_finished = float(d.get("finished", -1.0))

        obj.opened = float(d.get("opened", old_submitted))
        obj.launched = float(d.get("launched", old_started))
        obj.started = old_started
        obj.finished = old_finished
        obj.closed = float(d.get("closed", old_finished))

        obj._fill_defaults()
        return obj

    @property
    def submitted(self) -> float:
        return self.opened

    def open(self, at: float | None = None) -> None:
        self.opened = time.time() if at is None else float(at)

    def launch(self, at: float | None = None) -> None:
        self.launched = time.time() if at is None else float(at)
        if self.opened < 0:
            self.opened = self.launched

    def start(self, at: float | None = None) -> None:
        self.started = time.time() if at is None else float(at)
        if self.opened < 0:
            self.opened = self.started
        if self.launched < 0:
            self.launched = self.started

    def stop(self, at: float | None = None) -> None:
        self.finished = time.time() if at is None else float(at)
        if self.started < 0:
            self.started = self.finished
        if self.launched < 0:
            self.launched = self.started
        if self.opened < 0:
            self.opened = self.launched

    def close(self, at: float | None = None) -> None:
        self.closed = time.time() if at is None else float(at)
        if self.finished < 0:
            self.finished = self.closed
        if self.started < 0:
            self.started = self.finished
        if self.launched < 0:
            self.launched = self.started
        if self.opened < 0:
            self.opened = self.launched

    def queued(self, *, live: bool = False) -> float:
        return delta(self.opened, self.launched, live=live)

    def startup(self, *, live: bool = False) -> float:
        return delta(self.launched, self.started, live=live)

    def running(self, *, live: bool = False) -> float:
        return delta(self.started, self.finished, live=live)

    def teardown(self, *, live: bool = False) -> float:
        return delta(self.finished, self.closed, live=live)

    def duration(self, *, live: bool = False) -> float:
        """Backward-compatible alias for actual test execution time."""
        return self.running(live=live)

    def total(self, *, live: bool = False) -> float:
        return delta(self.opened, self.closed, live=live)

    def elapsed(self, *, live: bool = False) -> float:
        return self.total(live=live)

    def reset(self) -> None:
        self.opened = -1.0
        self.launched = -1.0
        self.started = -1.0
        self.finished = -1.0
        self.closed = -1.0

    def update(
        self,
        *,
        opened: float = -1.0,
        launched: float = -1.0,
        started: float = -1.0,
        finished: float = -1.0,
        closed: float = -1.0,
        submitted: float = -1.0,
    ) -> None:
        # ``submitted`` is accepted for backward compatibility.
        self.opened = float(opened if opened >= 0 else submitted)
        self.launched = float(launched)
        self.started = float(started)
        self.finished = float(finished)
        self.closed = float(closed)
        self._fill_defaults()

    def _fill_defaults(self) -> None:
        # Local/non-HPC defaults and old-state compatibility.
        if self.launched < 0 and self.started > 0:
            self.launched = self.started
        if self.closed < 0 and self.finished > 0:
            self.closed = self.finished
        if self.opened < 0:
            if self.launched > 0:
                self.opened = self.launched
            elif self.started > 0:
                self.opened = self.started


def delta(start: float, stop: float, *, live: bool = False) -> float:
    if start <= 0:
        return -1.0
    if stop > 0:
        return stop - start
    if live:
        return time.time() - start
    return -1.0
