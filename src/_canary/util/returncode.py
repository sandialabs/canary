# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Sequence

from . import logging

if TYPE_CHECKING:
    from ..testcase import TestCase

logger = logging.get_logger(__name__)


def compute_returncode(cases: Sequence["TestCase"], permissive: bool = False) -> int:
    returncode: int = 0

    results: dict[str, int] = {}
    for case in cases:
        results[case.status.name] = results.get(case.status.name, 0) + 1
    warned: set[str] = set()
    for result, n in results.items():
        for i in range(n):
            if result in ("SUCCESS", "XFAIL", "XDIFF"):
                continue
            elif result == "DIFFED":
                returncode |= 2**1
            elif result in ("FAILED", "ERROR"):
                returncode |= 2**2
            elif result == "TIMEOUT":
                returncode |= 2**3
            elif result in ("SKIPPED", "NOT_RUN"):
                returncode |= 2**4
            elif result in ("CANCELLED", "READY"):
                returncode |= 2**5
            elif not permissive:
                # any other code is a failure
                returncode |= 2**6
                if case.status.name not in warned:
                    logger.warning(f"{case}: unhandled status: {case.status}")
                    warned.add(case.status.name)
    return returncode
