import statistics

from ..test.case import TestCase
from ..test.status import Status
from . import logging


def progress(cases: list[TestCase], elapsed_time: float) -> None:
    """Display test session progress

    Args:
    ----------
    case : Active test cases

    """
    i = Status.members.index("cancelled")
    done = [c for c in cases if c.status.value in Status.members[i:]]
    times = [case.duration for case in done]
    average = None if not times else times[0] if len(times) == 1 else statistics.mean(times)
    logging.progress_bar(len(cases), len(done), elapsed_time, average)
