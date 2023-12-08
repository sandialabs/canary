from ..test.testcase import TestCase


def compute_returncode(cases: list[TestCase]) -> int:
    returncode: int = 0

    results: dict[str, int] = {}
    for case in cases:
        results[case.status.value] = results.get(case.status.value, 0) + 1
    for result, n in results.items():
        for i in range(n):
            if result == "diffed":
                returncode |= 2**1
            elif result == "failed":
                returncode |= 2**2
            elif result == "timeout":
                returncode |= 2**3
            elif result == "skipped":  # notdone
                returncode |= 2**4
            elif result == "staged":
                returncode |= 2**5
            elif result == "skipped":
                returncode |= 2**6
    return returncode
