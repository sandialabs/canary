# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Return-code computation for a collection of canary jobs.

``compute_returncode`` aggregates per-job statuses into a bitmask exit code
where each bit signals a specific failure class (diffed, timeout, failure,
cancelled, not-done, or other).
"""

from typing import TYPE_CHECKING
from typing import Sequence

from . import logging

if TYPE_CHECKING:
    from ..job import BaseJob

logger = logging.get_logger(__name__)


def compute_returncode(jobs: Sequence["BaseJob"], permissive: bool = False) -> int:
    """Compute a composite process exit code from the statuses of ``jobs``.

    Each failure class sets a specific bit in the return code:

    - Bit 1 (``2``): at least one job diffed.
    - Bit 2 (``4``): at least one job timed out.
    - Bit 3 (``8``): at least one job failed.
    - Bit 4 (``16``): at least one job was cancelled.
    - Bit 5 (``32``): at least one job did not finish.
    - Bit 6 (``64``): at least one job has an unhandled status (when not permissive).

    Successful and skipped jobs do not contribute to the code.

    Args:
        jobs: Sequence of job objects whose ``status`` and ``state`` are inspected.
        permissive: If ``True``, unrecognized statuses are silently ignored instead
            of setting bit 6.

    Returns:
        Bitmask exit code (0 means all jobs passed or were skipped).
    """
    returncode: int = 0
    warned: set[str] = set()
    for job in jobs:
        stat = job.status
        if stat.is_success() or stat.is_skipped():
            continue
        elif not job.state.is_done():
            returncode |= 2**5
        elif stat.is_diffed():
            returncode |= 2**1
        elif stat.is_timeout():
            returncode |= 2**2
        elif stat.is_failure():
            returncode |= 2**3
        elif stat.is_cancelled():
            returncode |= 2**4
        elif not permissive:
            # any other code is a failure
            returncode |= 2**6
            if stat.outcome.name not in warned:
                logger.warning(f"unhandled status: {stat.outcome.name}")
                warned.add(stat.outcome.name)
    return returncode
