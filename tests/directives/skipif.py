import os

import pytest

from _nvtest.error import StopExecution
from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_skipif(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import os
import sys
import nvtest
nvtest.directives.skipif(os.getenv('NVTEST_BAZ') is not None, reason='just because')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = NVTestCommand("run")
        rc = run("-w", ".")
        assert os.listdir("TestResults") == [".nvtest", "f1"]
        assert rc == 0
        with pytest.raises(StopExecution):
            # Error raised due to empty test session
            os.environ["NVTEST_BAZ"] = "1"
            rc = run("-w", "-o", "baz", ".")
        os.environ.pop("NVTEST_BAZ", None)
