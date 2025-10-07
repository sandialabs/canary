# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
from _canary.util.testing import CanaryCommand


def test_issue_80(tmpdir):
    with canary.filesystem.working_dir(tmpdir):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-80.vvt")
        run("-p", "dim=2D", f)
