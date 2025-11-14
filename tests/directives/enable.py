# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


def test_enable(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.enable(when='options=baz')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = CanaryCommand("run")
        # Non-zero return due to empty test session
        cp = run("-w", ".")
        assert cp.returncode == 7
        cp = run("-w", "-o", "baz", ".")
        assert set(os.listdir("TestResults")) == {"VIEW.TAG", "f1"}
        assert len(os.listdir("TestResults")) == 2
        assert cp.returncode == 0
