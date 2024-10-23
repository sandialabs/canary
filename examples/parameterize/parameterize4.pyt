import sys
import nvtest

nvtest.directives.parameterize("a,b", [(1, 1e5), (2, 1e6), (3, 1e7)])
nvtest.directives.parameterize("np", (4, 8))


def test():
    self = nvtest.test.instance
    print(f"running test with {self.parameters.a=}, {self.parameters.b=}, {self.parameters.np=}")


if __name__ == "__main__":
    sys.exit(test())
