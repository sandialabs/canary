import sys
import nvtest


def test():
    raise nvtest.TestSkipped()


if __name__ == "__main__":
    sys.exit(test())
