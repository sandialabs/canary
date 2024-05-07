import sys
import nvtest


def test():
    raise nvtest.TestFailed()


if __name__ == "__main__":
    sys.exit(test())
