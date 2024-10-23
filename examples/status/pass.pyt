import sys
import nvtest


nvtest.directives.keywords("fast")


def test():
    return 0


if __name__ == "__main__":
    sys.exit(test())
