import sys
import nvtest


nvtest.directives.xdiff()


def test():
    raise nvtest.TestDiffed()


if __name__ == "__main__":
    sys.exit(test())
