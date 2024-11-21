import os

import nvtest
from _nvtest.main import NVTestCommand


def test_issue_21(tmpdir):
    with nvtest.filesystem.working_dir(os.path.dirname(__file__)):
        run = NVTestCommand("run")
        rc = run("-d", os.path.join(tmpdir.strpath, "tests"), ".")
        assert rc == 0
