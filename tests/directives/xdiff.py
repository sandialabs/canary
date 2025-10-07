# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


def test_xdiff(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.xdiff()
def test():
    raise canary.TestDiffed()
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = CanaryCommand("run")
        cp = run("-w", ".")
        assert cp.returncode == 0
