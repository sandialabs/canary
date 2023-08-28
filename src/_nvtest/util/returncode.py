from ..test.testcase import TestCase


def compute_returncode(cases: list[TestCase]) -> int:
    returncode: int = 0

    results: dict[str, int] = {}
    for case in cases:
        results[case.result.name] = results.get(case.result.name, 0) + 1
    for (result, n) in results.items():
        for i in range(n):
            if result == "DIFF":
                returncode |= 2**1
            elif result == "FAIL":
                returncode |= 2**2
            elif result == "TIMEOUT":
                returncode |= 2**3
            elif result == "NOTDONE":
                returncode |= 2**4
            elif result == "NOTRUN":
                returncode |= 2**5
            elif result == "SKIP":
                returncode |= 2**6
    return returncode
