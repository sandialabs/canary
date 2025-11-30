# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import statistics
from typing import TYPE_CHECKING
from typing import Sequence

from . import logging

if TYPE_CHECKING:
    from ..protocols import JobProtocol


def progress(cases: Sequence["JobProtocol"], elapsed_time: float) -> None:
    """Display test session progress

    Args:
    ----------
    case : Active test cases

    """
    done = [c for c in cases if c.status.name not in ("PENDING", "READY", "RUNNING")]
    times = [case.timekeeper.duration for case in done if case.timekeeper.duration > 0]
    average = None if not times else times[0] if len(times) == 1 else statistics.mean(times)
    logging.progress_bar(len(cases), len(done), elapsed_time, average)
