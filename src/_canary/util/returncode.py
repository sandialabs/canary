# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Sequence

from . import logging

if TYPE_CHECKING:
    from ..job import BaseJob

logger = logging.get_logger(__name__)


def compute_returncode(jobs: Sequence["BaseJob"], permissive: bool = False) -> int:
    returncode: int = 0
    warned: set[str] = set()
    for job in jobs:
        if job.status.category_in(("PASS", "SKIP")):
            continue
        elif not job.state.is_done():
            returncode |= 2**5
        elif job.status.has_outcome("DIFFED"):
            returncode |= 2**1
        elif job.status.has_outcome("TIMEOUT"):
            returncode |= 2**2
        elif job.status.has_category("FAIL"):
            returncode |= 2**3
        elif job.status.has_category("CANCEL"):
            returncode |= 2**4
        elif not permissive:
            # any other code is a failure
            returncode |= 2**6
            if job.status.outcome not in warned:
                logger.warning(f"unhandled status: {job.status.outcome}")
                warned.add(job.status.outcome)
    return returncode
