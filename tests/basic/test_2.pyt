#!/usr/bin/env python3
import sys
import time

import nvtest

nvtest.mark.keywords("test_1", "baz", "spam")
nvtest.mark.parameterize("np,baz", [(1, "foo"), (2, "spam"), (8, "eggs")])
nvtest.mark.parameterize("method", (1, 2, 3))


def test():
    self = nvtest.test.instance
    if self.size == 8:
        raise nvtest.TestFailed("It is 8!")
    elif self.size == 2:
        raise nvtest.TestDiffed("It is 4")
    elif self.size == 1:
        raise nvtest.TestSkipped("It is 4")

    print("HERE I AM")
    print(self.name)
    print(self.size)
    print(self.parameters)
    time.sleep(.1)


if __name__ == "__main__":
    sys.exit(test())
