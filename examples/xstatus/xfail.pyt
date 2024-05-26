import sys
import nvtest


nvtest.directives.keywords("fast")
nvtest.directives.xfail()


def test():
    raise nvtest.TestFailed()


if __name__ == "__main__":
    sys.exit(test())
