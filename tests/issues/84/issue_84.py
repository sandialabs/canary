# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys

import canary


def test_issue_84(tmpdir):
    with canary.filesystem.working_dir(tmpdir):
        with open("canary.yaml", "w") as fh:
            fh.write("test:\n  timeout:\n    baz: 4m")
        f = os.path.join(os.path.dirname(__file__), "issue-84.pyt")
        with open(os.path.basename(f), "w") as fh:
            fh.write(open(f).read())
        args = [sys.executable, "-m", "canary", "run", "."]
        cp = subprocess.run(args)
        if cp.returncode != 0:
            print(open("TestResults/issue-84/canary-run-out.txt").read())
        assert cp.returncode == 0
