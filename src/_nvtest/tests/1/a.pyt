#!/usr/bin/env python3
import sys
import time

import nvtest

nvtest.directives.skipif(sys.platform == "darwin", reason="Test does not run on Darwin")
nvtest.directives.keywords("baz", "spam")
nvtest.directives.parameterize("np,baz", [(1, "foo"), (2, "spam"), (8, "eggs")], options="opt")
nvtest.directives.parameterize("method", (1, 2, 3), platforms="darwin")


def test():
    self = nvtest.test.instance
    if self.size == 8:
        raise nvtest.TestFailed("It is 8!")
    elif self.size == 2:
        raise nvtest.TestDiffed("It is 4")

    print("HERE I AM")
    print(self.name)
    print(self.size)
    print(self.parameters)
    time.sleep(.1)


if __name__ == "__main__":
    sys.exit(test())
