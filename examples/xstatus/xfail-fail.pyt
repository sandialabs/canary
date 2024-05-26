import sys
import nvtest


nvtest.directives.keywords("fast")
nvtest.directives.xfail()


def test():
    # This test should fail
    return 0


if __name__ == "__main__":
    sys.exit(test())
