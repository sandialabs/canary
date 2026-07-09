import sys

import canary

canary.directives.exclusive()


def test():
    return 0


if __name__ == "__main__":
    sys.exit(test())
