# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys

import canary


def test_issue_84(tmpdir):
    with canary.filesystem.working_dir(tmpdir):
        f = os.path.join(os.path.dirname(__file__), "issue-84.pyt")
        with open(os.path.basename(f), "w") as fh:
            fh.write(open(f).read())
        args = [sys.executable, "-m", "canary", "init", "."]
        subprocess.run(args)
        args = [sys.executable, "-m", "canary", "add", "."]
        subprocess.run(args)
        with open(".canary/config.yaml", "w") as fh:
            fh.write("canary:\n  timeout:\n    baz: 4m")
        args = [sys.executable, "-m", "canary", "generate"]
        subprocess.run(args)
        args = [sys.executable, "-m", "canary", "run"]
        cp = subprocess.run(args)
        assert cp.returncode == 0
