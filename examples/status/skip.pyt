import sys

import nvtest

nvtest.directives.keywords("fast")


def test():
    raise nvtest.TestSkipped()


if __name__ == "__main__":
    sys.exit(test())
