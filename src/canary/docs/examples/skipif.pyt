import sys

import canary_pyt

canary_pyt.directives.skipif(True, reason="intentional skipif example")


def test():
    raise RuntimeError("should not run")


if __name__ == "__main__":
    sys.exit(test())
