# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
from _canary.main import CanaryCommand


def test_issue_21(tmpdir):
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-21.vvt")
        rc = run("-d", os.path.join(tmpdir.strpath, "21.0"), f)
        assert rc == 0
