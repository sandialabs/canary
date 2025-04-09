# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import os
import re

from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_batched(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import canary
canary.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = CanaryCommand("run")
        rc = run("-w", "-b", "spec=count:4", "-b", "scheduler=none", ".")
        dirs = os.listdir("TestResults")
        expected = [".canary"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        files = glob.glob("TestResults/.canary/batches/**/canary-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob("TestResults/.canary/batches/**/canary-out.txt", recursive=True)
        assert len(files) == 4
        assert rc == 0


def test_batched_extra_args(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import canary
canary.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = CanaryCommand("run")
        args = ["-w", "-b", "spec=count:4", "-b", "scheduler=none"]
        args.extend(["-b", "args='-l place=scatter:excl,-q debug,-A XYZ123'"])
        args.append(".")
        rc = run(*args)
        dirs = os.listdir("TestResults")
        expected = [".canary"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        files = glob.glob("TestResults/.canary/batches/**/canary-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob("TestResults/.canary/batches/**/canary-inp.sh", recursive=True)
        found = 0
        print(open(files[0]).read())
        for line in open(files[0]):
            if re.search(r"#\s*BASH:? -l place=scatter:excl", line):
                found += 1
            elif re.search(r"#\s*BASH:? -q debug", line):
                found += 1
            elif re.search(r"#\s*BASH:? -A XYZ123", line):
                found += 1
        assert found == 3
        if rc != 0:
            print(open(files[0], "r").read())
        assert len(files) == 4
        files = glob.glob("TestResults/.canary/batches/**/canary-out.txt", recursive=True)
        assert len(files) == 4
        if rc != 0:
            print(open(files[0], "r").read())
        assert rc == 0
