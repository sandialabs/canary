import os

import pytest

from _nvtest.error import StopExecution
from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_enable(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import sys
import nvtest
nvtest.directives.enable(when='options=baz')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = NVTestCommand("run")
        with pytest.raises(StopExecution):
            # Error raised due to empty test session
            rc = run("-w", ".")
        rc = run("-w", "-o", "baz", ".")
        if os.getenv("VVTEST_PATH_NAMING_CONVENTION", "yes").lower() in ("yes", "true", "1", "on"):
            assert os.listdir("TestResults") == [".nvtest", "f1"]
        assert len(os.listdir("TestResults")) == 2
        assert rc == 0
