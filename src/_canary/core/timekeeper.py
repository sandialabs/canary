# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Lifecycle timestamp tracker for a single job execution.

:class:`Timekeeper` records five Unix timestamps that bracket the canonical
job lifecycle (submitted → staged → started → stopped → finished) and exposes
them as four named time phases plus a running ``elapsed`` total.

The module-level :func:`delta` helper computes a phase duration, returning
``-1.0`` when the phase is not yet complete and optionally measuring against
``time.time()`` for a live (in-progress) reading.
"""

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
        """Serialize all timestamp fields to a plain dict of floats."""
        return dict(vars(self))

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "Timekeeper":
        """Reconstruct a ``Timekeeper`` from a serialized dict of floats."""
        obj = cls()
        for var, val in d.items():
            setattr(obj, var, val)
        return obj

    def open(self, at: float | None = None) -> None:
        """Record the submission timestamp and reset all other timestamps.

        Args:
            at: Explicit Unix timestamp; defaults to ``time.time()``.
        """
        self.reset()
        self._submitted = time.time() if at is None else float(at)

    def maybe_open(self, at: float | None = None) -> None:
        """Call :meth:`open` only if the submission timestamp has not been set yet."""
        if self._submitted < 0:
            self.open(at=at)

    def stage(self, at: float | None = None) -> None:
        """Record the staging (setup-start) timestamp.

        Also sets :attr:`_submitted` to the same value if it has not been
        recorded yet.

        Args:
            at: Explicit Unix timestamp; defaults to ``time.time()``.
        """
        self._staged = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._staged

    def maybe_stage(self, at: float | None = None) -> None:
        """Call :meth:`stage` only if the staging timestamp has not been set yet."""
        if self._staged < 0:
            self.stage(at=at)

    def start(self, at: float | None = None) -> None:
        """Record the execution-start timestamp.

        Backfills :attr:`_submitted` and :attr:`_staged` if not already set.

        Args:
            at: Explicit Unix timestamp; defaults to ``time.time()``.
        """
        self._started = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._started
        if self._staged < 0:
            self._staged = self._started

    def maybe_start(self, at: float | None = None) -> None:
        """Call :meth:`start` only if the start timestamp has not been set yet."""
        if self._started < 0:
            self.start(at=at)

    def stop(self, at: float | None = None) -> None:
        """Record the execution-stop timestamp.

        Backfills :attr:`_submitted`, :attr:`_staged`, and :attr:`_started` if
        not already set.

        Args:
            at: Explicit Unix timestamp; defaults to ``time.time()``.
        """
        self._stopped = time.time() if at is None else float(at)
        if self._submitted < 0:
            self._submitted = self._stopped
        if self._staged < 0:
            self._staged = self._stopped
        if self._started < 0:
            self._started = self._stopped

    def maybe_stop(self, at: float | None = None) -> None:
        """Call :meth:`stop` only if the stop timestamp has not been set yet."""
        if self._stopped < 0:
            self.stop(at=at)

    def close(self, at: float | None = None) -> None:
        """Record the teardown-complete (finished) timestamp.

        Backfills all earlier timestamps if not already set, so a job that
        finishes without going through the full lifecycle still records
        consistent (if inaccurate) phase boundaries.

        Args:
            at: Explicit Unix timestamp; defaults to ``time.time()``.
        """
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
        """Call :meth:`close` only if the finished timestamp has not been set yet."""
        if self._finished < 0:
            self.close(at=at)

    finish = close

    def pending(self, *, live: bool = False) -> float:
        """Duration of the *pending* phase (submitted → staged).

        Args:
            live: If ``True`` and staging has not completed, measure against
                ``time.time()`` instead of returning ``-1.0``.

        Returns:
            Phase duration in seconds, or ``-1.0`` if not yet started.
        """
        return delta(self._submitted, self._staged, live=live)

    def staging(self, *, live: bool = False) -> float:
        """Duration of the *setup* phase (staged → started).

        Args:
            live: If ``True`` and start has not been recorded, measure live.

        Returns:
            Phase duration in seconds, or ``-1.0`` if not applicable.
        """
        return delta(self._staged, self._started, live=live)

    def running(self, *, live: bool = False) -> float:
        """Duration of the *running* phase (started → stopped).

        Args:
            live: If ``True`` and the job is still running, measure live.

        Returns:
            Phase duration in seconds, or ``-1.0`` if not started.
        """
        return delta(self._started, self._stopped, live=live)

    duration = running

    def finishing(self, *, live: bool = False) -> float:
        """Duration of the *teardown* phase (stopped → finished).

        Args:
            live: If ``True`` and teardown has not completed, measure live.

        Returns:
            Phase duration in seconds, or ``-1.0`` if not applicable.
        """
        return delta(self._stopped, self._finished, live=live)

    def total(self, *, live: bool = False) -> float:
        """Total elapsed wall time from submission to finish (submitted → finished).

        Args:
            live: If ``True`` and the job has not finished, measure live.

        Returns:
            Total duration in seconds, or ``-1.0`` if submission not recorded.
        """
        return delta(self._submitted, self._finished, live=live)

    def elapsed(self, *, live: bool = False) -> float:
        """Alias for :meth:`total`; total elapsed time since submission."""
        return self.total(live=live)

    def reset(self) -> None:
        """Reset all timestamps to ``-1.0`` (unset)."""
        for var in vars(self):
            setattr(self, var, -1.0)

    def update(self, **kwargs: float) -> None:
        """Update named timestamp fields from keyword arguments.

        Accepts ``submitted``, ``staged``, ``started``, ``stopped``, and
        ``finished`` (plus legacy aliases ``launched`` for ``submitted``).

        Args:
            **kwargs: Mapping of field name → Unix timestamp float.
        """
        for key, val in kwargs.items():
            setattr(self, key, float(val))

    def sync(self, other: "Timekeeper") -> None:
        """Copy all timestamp values from *other* into this instance.

        Args:
            other: The source ``Timekeeper`` whose values will overwrite ours.
        """
        for var, value in vars(other).items():
            setattr(self, var, float(value))


def delta(start: float, stop: float, *, live: bool = False) -> float:
    """Compute the duration between two timestamps.

    Args:
        start: Unix timestamp of the phase start (``-1.0`` if unset).
        stop: Unix timestamp of the phase end (``-1.0`` if unset).
        live: If ``True`` and *stop* is unset, return ``time.time() - start``
            instead of ``-1.0``.

    Returns:
        Duration in seconds, or ``-1.0`` if the phase has not started or
        completed (and ``live`` is ``False``).
    """
    if start <= 0:
        return -1.0
    if stop > 0:
        return stop - start
    if live:
        return time.time() - start
    return -1.0
