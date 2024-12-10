import sys
import time

import nvtest

nvtest.directives.keywords("fast")
nvtest.directives.timeout(0.1)


def test():
    time.sleep(5)


if __name__ == "__main__":
    sys.exit(test())
