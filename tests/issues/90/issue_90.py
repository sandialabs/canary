import os

import _canary.util.filesystem as fs
from _canary.util.testing import CanaryCommand


def test_issue_90(tmpdir):
    run = CanaryCommand("run")
    rerun = CanaryCommand("rerun")
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            write_testfile(fh)
        cp = run("-w", ".", check=False, debug=True)
        assert cp.returncode != 0
        try:
            os.environ["FIX_B"] = "1"
            cp = rerun("b", debug=True)
        finally:
            os.environ.pop("FIX_B")
        assert cp.returncode == 0
        assert set(os.listdir("TestResults")) == {"VIEW.TAG", "a", "b", "c"}


def write_testfile(file):
    file.write("""\
import os
import sys
import canary

canary.directives.name("a")
canary.directives.name("b")
canary.directives.name("c")

canary.directives.depends_on("c", when="testname=b")
canary.directives.depends_on("b", when="testname=a")


def test():
    self = canary.get_instance()
    if self.name == "b" and not os.getenv('FIX_B'):
        assert 0, "b fails"


if __name__ == "__main__":
    sys.exit(test())
""")
