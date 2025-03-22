import os

import canary
from _canary.plugins.generators.pyt import PYTTestGenerator


def test_issue_47(tmpdir):
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        file = PYTTestGenerator(".", "issue-62.pyt")
        cases = file.lock(on_options=[])
        assert len(cases) == 3
        assert len([case for case in cases if not case.masked()]) == 2
