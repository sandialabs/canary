import os

import canary
from _canary.main import CanaryCommand


def test_issue_20_0(tmpdir):
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-20-0.vvt")
        rc = run("-d", os.path.join(tmpdir.strpath, "20.0"), f)
        assert rc == 6


def test_issue_20_1(tmpdir):
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        run = CanaryCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-20-1.vvt")
        rc = run("-d", os.path.join(tmpdir.strpath, "21.1"), f)
        # some tests intentionally fail, so a non-zero returncode is expected:
        assert rc == 22
