#!/usr/bin/env python3
import os
import sys
import time

import nvtest

nvtest.mark.name("test_1.alt")
nvtest.mark.keywords("baz", "spam")
nvtest.mark.analyze(True, testname="test_1.alt")
nvtest.mark.timeout(1.0)
nvtest.mark.skipif(False, reason="Because")
nvtest.mark.parameterize("np,baz", [(1, "foo"), (2, "spam"), (8, "eggs")])
nvtest.mark.parameterize("method", (1, 2, 3))
nvtest.mark.copy("{name}.inp", testname="test_1.alt")
nvtest.mark.link("{name}.txt", testname="test_1.alt")


def test():
    self = nvtest.test.instance
    if self.family == "test_1.alt":
        assert os.path.isfile("./test_1.alt.inp")
        assert os.path.islink("./test_1.alt.txt")
    else:
        assert not os.path.isfile("./test_1.alt.inp"), self.name
        assert not os.path.islink("./test_1.alt.txt"), self.name
    if self.size == 8:
        raise ValueError("It is 8!")
    print("HERE I AM")
    print(self.name)
    print(self.size)
    print(self.parameters)
    time.sleep(.1)


def analyze():
    self = nvtest.test.instance
    for dep in self.dependencies:
        assert os.path.exists(dep.exec_dir)
        if dep.parameters["np"] == 8:
            assert dep.result == nvtest.Result.FAIL
        else:
            assert dep.result == nvtest.Result.PASS


def main():
    if "--analyze" in sys.argv[1:]:
        return analyze()
    return test()

if __name__ == "__main__":
    sys.exit(main())
