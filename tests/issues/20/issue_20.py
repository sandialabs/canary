# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
from _canary.util.testing import CanaryCommand


def test_issue_20_0(tmpdir):
    with canary.filesystem.working_dir(tmpdir.strpath, create=True):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-20-0.vvt")
        cp = run(f, debug=True)
        assert cp.returncode == 6


def test_issue_20_1(tmpdir):
    with canary.filesystem.working_dir(tmpdir.strpath, create=True):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-20-1.vvt")
        cp = run(f)
        # some tests intentionally fail, so a non-zero returncode is expected:
        assert cp.returncode == 6
