import os

import _canary.util.filesystem as fs
from _canary.main import CanaryCommand


def test_issue_90(tmpdir):
    run = CanaryCommand("run")
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            write_testfile(fh)
        rc = run("-w", ".", fail_on_error=False)
        assert rc != 0
        with fs.working_dir("TestResults"):
            try:
                os.environ["FIX_B"] = "1"
                rc = run("-k", "not success", ".", fail_on_error=False)
            finally:
                os.environ.pop("FIX_B")
            assert rc == 0
            assert os.path.exists("a/canary-out.txt")


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
