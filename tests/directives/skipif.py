# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest

from _canary.error import StopExecution
from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_skipif(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import os
import sys
import canary
canary.directives.skipif(os.getenv('CANARY_BAZ') is not None, reason='just because')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = CanaryCommand("run")
        rc = run("-w", ".")
        assert os.listdir("TestResults") == [".canary", "f1"]
        assert len(os.listdir("TestResults")) == 2
        assert rc == 0
        with pytest.raises(StopExecution):
            # Error raised due to empty test session
            os.environ["CANARY_BAZ"] = "1"
            rc = run("-w", "-o", "baz", ".")
        os.environ.pop("CANARY_BAZ", None)
