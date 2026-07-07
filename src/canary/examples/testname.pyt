import sys

import canary

canary.directives.testname("alpha")
canary.directives.testname("beta")


def test():
    self = canary.get_instance()
    assert self.family in ("alpha", "beta")
    return 0


if __name__ == "__main__":
    sys.exit(test())
