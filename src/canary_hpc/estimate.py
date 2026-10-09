# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Conservative per-job runtime estimates used to pack batches and size their wall limits.

The estimate does not need to be accurate: the in-batch queue executor does the
real scheduling, and packing only needs estimates that are consistent enough to
produce batches of roughly equal runtime.  It must not be *optimistic*, however,
because the scheduler wall limit of each batch is derived from it and a wall
limit shorter than the real runtime kills the batch.
"""

from typing import Any
from typing import Protocol

import canary


class EstimableJob(Protocol):
    """The parts of a job the runtime estimate depends on."""

    @property
    def id(self) -> str: ...

    @property
    def timeout(self) -> float: ...

    def total_timeout(self) -> float: ...

    def load_cached_runs(self) -> dict[str, Any] | None: ...


#: Runtime estimate for a job with no timing history, as a fraction of its
#: declared timeout.  Declared timeouts are an upper limit, not a runtime
#: prediction, and the fraction of it that a job actually uses varies widely,
#: so the cold estimate is deliberately conservative.  Override with
#: ``--batch-cold-runtime-fraction``.
DEFAULT_COLD_RUNTIME_FRACTION: float = 0.75

#: Lower bound for an estimate drawn from timing history, as a fraction of the
#: declared timeout.  Guards against a history made of anomalously fast runs
#: (e.g. an aborted run that still reported success).
RUNTIME_FLOOR_FRACTION: float = 0.1

#: Safety penalty applied to an estimate drawn from timing history.  Runtimes
#: vary from run to run (machine load, filesystem contention), so a historical
#: sample is inflated before it is used.
RUNTIME_HISTORY_PENALTY: float = 1.25

logger = canary.get_logger(__name__)


def cold_runtime_fraction() -> float:
    """Return the fraction of the timeout used to estimate a job with no history."""
    value = canary.config.getoption("hpc_batch_cold_runtime_fraction")
    if value is None:
        return DEFAULT_COLD_RUNTIME_FRACTION
    return float(value)


def historical_runtime(job: EstimableJob) -> float | None:
    """Return the longest representative runtime recorded for ``job``, or ``None``.

    Uses ``max(mean, max)`` rather than the mean alone so that a few anomalously
    fast samples cannot drag the estimate down.
    """
    try:
        cache = job.load_cached_runs()
    except Exception:
        logger.debug("Failed to load historic timing data for %s", job.id[:7], exc_info=True)
        return None
    if not cache:
        return None
    try:
        stats = cache["metrics"]["time"]
        return max(float(stats["mean"]), float(stats.get("max", 0.0)))
    except (KeyError, TypeError, ValueError):
        return None


def estimate_runtime(job: EstimableJob) -> float:
    """Return a conservative runtime estimate for ``job``, in seconds.

    * With timing history: ``max(PENALTY * history, FLOOR * timeout)``.
    * Without history: ``cold_fraction * timeout``.

    Either way the estimate is capped at ``job.total_timeout()``: the job is
    killed at that point, so it can never run longer.
    """
    timeout = float(job.timeout)
    ceiling = float(job.total_timeout())
    sample = historical_runtime(job)
    if sample is None:
        estimate = cold_runtime_fraction() * timeout
    else:
        estimate = max(RUNTIME_HISTORY_PENALTY * sample, RUNTIME_FLOOR_FRACTION * timeout)
    return min(estimate, ceiling)
