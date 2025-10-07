# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


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
        cp = run("-w", ".")
        assert set(os.listdir("TestResults")) == {".canary", "f1"}
        assert len(os.listdir("TestResults")) == 2
        assert cp.returncode == 0
        os.environ["CANARY_BAZ"] = "1"
        cp = run("-w", "-o", "baz", ".")
        assert cp.returncode == 7
        os.environ.pop("CANARY_BAZ", None)
