import sys
import time

import nvtest

nvtest.directives.timeout(0.5)


def test() -> int:
    time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(test())
