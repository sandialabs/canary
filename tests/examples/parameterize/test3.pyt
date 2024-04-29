import sys
import nvtest

nvtest.directives.parameterize("a", (1, 4))
nvtest.directives.parameterize("b", (1.e5, 1.e6, 1.e7))

def test():
   self = nvtest.test.instance
   print(f"running test with {self.parameters.a=} and {self.parameters.b=}")


if __name__ == "__main__":
   sys.exit(test())
