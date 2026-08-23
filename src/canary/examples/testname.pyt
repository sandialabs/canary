import sys

import canary
import canary_pyt

canary_pyt.directives.testname("alpha")
canary_pyt.directives.testname("beta")


def test():
    self = canary.get_instance()
    assert self.family in ("alpha", "beta")
    return 0


if __name__ == "__main__":
    sys.exit(test())
