import os

import nvtest
from _nvtest.main import NVTestCommand


def test_issue_21(tmpdir):
    with nvtest.filesystem.working_dir(os.path.dirname(__file__)):
        run = NVTestCommand("run")
        f = os.path.join(os.path.dirname(__file__), "issue-21.vvt")
        rc = run("-d", os.path.join(tmpdir.strpath, "21.0"), f)
        assert rc == 0
