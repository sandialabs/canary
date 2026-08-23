import sys

import canary_pyt

canary_pyt.directives.exclusive()


def test():
    return 0


if __name__ == "__main__":
    sys.exit(test())
