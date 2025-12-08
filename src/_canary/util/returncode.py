# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Sequence

from . import logging

if TYPE_CHECKING:
    from ..protocols import JobProtocol
    from ..testcase import TestCase

logger = logging.get_logger(__name__)


def compute_returncode(cases: Sequence["JobProtocol | TestCase"], permissive: bool = False) -> int:
    returncode: int = 0

    results: dict[str, int] = {}
    for case in cases:
        results[case.status.category] = results.get(case.status.category, 0) + 1
    warned: set[str] = set()
    for result, n in results.items():
        for i in range(n):
            if result in ("SUCCESS", "XFAIL", "XDIFF", "SKIPPED"):
                continue
            elif result == "DIFFED":
                returncode |= 2**1
            elif result in ("FAILED", "ERROR", "BROKEN"):
                returncode |= 2**2
            elif result == "TIMEOUT":
                returncode |= 2**3
            elif result in ("CANCELLED", "READY", "PENDING", "BLOCKED"):
                returncode |= 2**5
            elif not permissive:
                # any other code is a failure
                returncode |= 2**6
                if result not in warned:
                    logger.warning(f"unhandled status: {result}")
                    warned.add(result)
    return returncode
