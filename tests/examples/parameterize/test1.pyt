import sys
import nvtest

nvtest.directives.parameterize("a", (1, 4))

def test():
   self = nvtest.test.instance
   print(f"{self.parameters.a}")

if __name__ == "__main__":
   sys.exit(test())
