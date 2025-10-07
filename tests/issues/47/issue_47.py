# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
from _canary.util.testing import CanaryCommand


def test_issue_47(tmpdir):
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-47.vvt")
        cp = run("-d", os.path.join(tmpdir.strpath, "47"), f)
        assert cp.returncode == 0
        files = os.listdir(os.path.join(tmpdir.strpath, "47"))
        assert len(files) == 7
        assert set(files) == {
            ".canary",
            "test2.arg3=apple",
            "test2.arg3=strawberry",
            "test4.arg1=pear.arg2=kiwi",
            "test4.arg1=pear.arg2=pineapple",
            "test4.arg1=plum.arg2=kiwi",
            "test4.arg1=plum.arg2=pineapple",
        }
