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
