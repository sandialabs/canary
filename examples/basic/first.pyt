import sys
import nvtest

nvtest.directives.keywords("basic", "first")


def add(a: int, b: int) -> int:
    return a + b


def test():
    assert add(3, 2) == 5


if __name__ == "__main__":
    sys.exit(test())
