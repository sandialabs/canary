import sys

import nvtest

nvtest.directives.keywords("fast")
nvtest.directives.xfail(code=23)


def test():
    return 23


if __name__ == "__main__":
    sys.exit(test())
