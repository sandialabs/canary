# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import statistics
from typing import TYPE_CHECKING
from typing import Sequence

from ..status import Status
from . import logging

if TYPE_CHECKING:
    from ..testcase import TestCase


def progress(cases: Sequence["TestCase"], elapsed_time: float) -> None:
    """Display test session progress

    Args:
    ----------
    case : Active test cases

    """
    i = Status.members.index("cancelled")
    done = [c for c in cases if c.status.value in Status.members[i:]]
    times = [case.duration for case in done if case.duration > 0]
    average = None if not times else times[0] if len(times) == 1 else statistics.mean(times)
    logging.progress_bar(len(cases), len(done), elapsed_time, average)
