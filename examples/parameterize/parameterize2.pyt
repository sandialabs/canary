import sys

import nvtest

nvtest.directives.parameterize("a,b", [(1, 2), (5, 6)])


def test():
    self = nvtest.test.instance
    print(f"{self.parameters.a=}, {self.parameters.b=}")


if __name__ == "__main__":
    sys.exit(test())
