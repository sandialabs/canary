# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING

from ..util import logging
from .store import HistoryStore

if TYPE_CHECKING:
    from .store import RetrievableJob

logger = logging.get_logger(__name__)

#: Runtime estimate for a job with no timing history, as a fraction of its
#: declared timeout.  Declared timeouts are an upper limit, not a runtime
#: prediction, and the fraction of it that a job actually uses varies widely,
#: so the cold estimate is deliberately conservative.  Override with
#: ``--batch-cold-runtime-fraction``.
COLD_RUNTIME_FRACTION: float = 0.75


def estimate_runtime(
    job: "RetrievableJob", store: HistoryStore | None = None, safety_factor: float = 0.5
) -> float:
    """Return a conservative runtime estimate for ``job``, in seconds."""
    import math

    if store is not None and (stats := store.runtime_statistics(job)):
        stddev = math.sqrt(max(0.0, stats.variance))
        return stats.mean + safety_factor * stddev
    else:
        return COLD_RUNTIME_FRACTION * job.timeout
