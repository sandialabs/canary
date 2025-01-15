import sys

import canary

canary.directives.keywords("fast")
canary.directives.xfail()


def test():
    raise canary.TestFailed()


if __name__ == "__main__":
    sys.exit(test())
