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
        args = [sys.executable, "-m", "canary", "config", "set", "--local", "run:timeout:baz", "4m"]
        subprocess.run(args)
        args = [sys.executable, "-m", "canary", "selection", "create", "-r", ".", "my-selection"]
        subprocess.run(args)
        args = [sys.executable, "-m", "canary", "run", "my-selection"]
        cp = subprocess.run(args)
        if cp.returncode != 0:
            print(os.listdir("TestResults"))
            print(open("TestResults/issue-84/canary-out.txt").read())
            print(open(".canary/config.yaml").read())
        assert cp.returncode == 0
