import sys

import canary

canary.directives.keywords("fast")


def test():
    return 0


if __name__ == "__main__":
    sys.exit(test())
