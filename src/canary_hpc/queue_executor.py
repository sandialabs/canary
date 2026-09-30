# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import time
from typing import Any
from typing import Protocol
from typing import cast

from _canary.core.job import JobPhase
from _canary.execution.queue_executor import ExecutionSlot
from _canary.execution.queue_executor import ResourceQueueExecutor
from _canary.util import logging

logger = logging.get_logger(__name__)


class _BatchJobProtocol(Protocol):
    """Structural protocol for HPC batch jobs that support child-status reconciliation."""

    _allocation: dict[str, Any]

    def finalize_status_from_child_jobs(self) -> None: ...

    @property
    def status(self) -> Any: ...

    @property
    def state(self) -> Any: ...

    def save(self) -> None: ...

    @property
    def id(self) -> str: ...


class HPCResourceQueueExecutor(ResourceQueueExecutor):
    """ResourceQueueExecutor specialized for HPC batches."""

    def _finish_abnormal_slot(
        self, slot: ExecutionSlot, *, outcome: str, reason: str, code: int = -1
    ) -> None:
        """
        Finish a slot for abnormal executor-side terminal events.

        For HPC batches (jobs that expose a ``finalize_status_from_child_jobs``
        method) we first refresh child lockfiles from disk.  If all children
        have already reached a terminal state the batch status is derived from
        the real child outcomes rather than the abnormal executor event; the
        abnormal event is recorded as a warning so the discrepancy is visible
        in logs.  This handles the case where the worker process was killed by
        the outer watchdog after the scheduler already completed the batch but
        before the subprocess could send ``job_finished``.
        """
        now = time.time()
        try:
            slot.job.refresh()
        except Exception as e:
            logger.debug("job.refresh failed during abnormal finish: %s", e)

        # For HPC batches: check whether all child jobs finished successfully
        # on disk before trusting the abnormal executor-level outcome.
        if hasattr(slot.job, "finalize_status_from_child_jobs"):
            batch_job = cast(_BatchJobProtocol, slot.job)
            try:
                batch_job.finalize_status_from_child_jobs()
                if not batch_job.status.is_unset():
                    # Children have a real terminal status — use it and warn.
                    logger.warning(
                        "Batch %s: abnormal executor event (%s: %s) but child "
                        "jobs have terminal status %s — using child-derived "
                        "status.  The worker process may have been killed after "
                        "the scheduler job completed.",
                        batch_job.id[:7],
                        outcome,
                        reason,
                        batch_job.status.outcome.name,
                    )
                    batch_job.state.phase = JobPhase.DONE
                    batch_job._allocation["state"] = "inactive"
                    try:
                        batch_job.save()
                    except Exception as e:
                        logger.debug("job.save failed after child reconciliation: %s", e)
                    return
            except Exception as e:
                logger.debug("finalize_status_from_child_jobs failed during abnormal finish: %s", e)

        super()._finish_abnormal_slot(slot, outcome=outcome, reason=reason, code=code)
