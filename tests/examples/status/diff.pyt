import sys
import nvtest


def test():
    raise nvtest.TestDiffed()


if __name__ == "__main__":
    sys.exit(test())
