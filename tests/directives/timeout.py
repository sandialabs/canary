# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_timeout(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import sys
import time
import canary
canary.directives.timeout('1us')
def test():
    time.sleep(1)
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = CanaryCommand("run")
        rc = run("-w", ".")
        assert rc == 8
