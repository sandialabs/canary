# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
from _canary.main import CanaryCommand


def test_issue_80(tmpdir):
    with canary.filesystem.working_dir(tmpdir):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-80.vvt")
        rc = run("-p", "dim=2D", f)
