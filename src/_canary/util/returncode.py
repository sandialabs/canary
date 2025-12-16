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
    warned: set[str] = set()
    for case in cases:
        if case.status.category in ("PASS", "SKIP"):
            continue
        elif case.status.status == "DIFFED":
            returncode |= 2**1
        elif case.status.status == "TIMEOUT":
            returncode |= 2**2
        elif case.status.category == "FAIL":
            returncode |= 2**3
        elif case.status.category == "CANCEL":
            returncode |= 2**4
        elif case.status.state in ("READY", "PENDING"):
            returncode |= 2**5
        elif not permissive:
            # any other code is a failure
            returncode |= 2**6
            if case.status.status not in warned:
                logger.warning(f"unhandled status: {case.status.status}")
                warned.add(case.status.status)
    return returncode
