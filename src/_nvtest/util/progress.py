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
    done = [case for case in cases if case.status.value in Status.members[i:]]
    average = None if not done else statistics.mean([c.duration for c in done if c.duration > 0])
    logging.progress_bar(len(cases), len(done), elapsed_time, average)
