import sys

def add(a: int, b: int) -> int:
    return a + b


def test() -> int:
    assert add(2, 3) == 5
    return 0

if __name__ == "__main__":
    sys.exit(test())
