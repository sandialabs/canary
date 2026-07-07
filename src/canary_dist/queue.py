# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import cast

import canary
from canary_hpc import queue

from .batchspec import TestBatch

logger = canary.get_logger(__name__)


class ResourceQueue(queue.ResourceQueue):
    def done(self, job: canary.BaseJob) -> None:
        batch = cast(TestBatch, job)
        with self.lock:
            if batch.id not in self._busy:
                raise RuntimeError(f"Job {batch} is not running")
            self._finished[batch.id] = self._busy.pop(batch.id)
            if batch.exclusive:
                self.exclusive_job_id = None
                logger.debug(f"Exclusive job {batch.id} finished, exclusive lock released")
            allocation = batch.free_resources()
            self.rpool.checkin(allocation)  # type: ignore[arg-type]
            logger.debug(f"Job {batch.id} marked done")
