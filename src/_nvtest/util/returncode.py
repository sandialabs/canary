from typing import Sequence

from ..test.case import TestCase


def compute_returncode(cases: Sequence[TestCase]) -> int:
    returncode: int = 0

    results: dict[str, int] = {}
    for case in cases:
        results[case.status.value] = results.get(case.status.value, 0) + 1
    for result, n in results.items():
        for i in range(n):
            if result in ("success", "xfail", "xdiff"):
                continue
            elif result == "diffed":
                returncode |= 2**1
            elif result == "failed":
                returncode |= 2**2
            elif result == "timeout":
                returncode |= 2**3
            elif result == "skipped":  # notdone
                returncode |= 2**4
            elif result == "ready":
                returncode |= 2**5
            elif result == "skipped":
                returncode |= 2**6
            elif result == "cancelled":
                returncode |= 2**7
            elif result == "not_run":
                returncode |= 2**8
    return returncode
