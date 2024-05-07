import sys
import nvtest


nvtest.directives.xdiff()


def test():
    # This test should fail
    return 0


if __name__ == "__main__":
    sys.exit(test())
