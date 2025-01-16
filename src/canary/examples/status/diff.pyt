import sys

import canary

canary.directives.keywords("fast")


def test():
    raise canary.TestDiffed()


if __name__ == "__main__":
    sys.exit(test())
