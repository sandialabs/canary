import os

from _nvtest.main import NVTestCommand
from _nvtest.util import shell
from _nvtest.util.filesystem import working_dir


def test_source_rcfile_1(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("file.sh", "w") as fh:
            fh.write("export BAZ=SPAM\n")
        with open("file.pyt", "w") as fh:
            fh.write("""\
import nvtest
import os
import sys
nvtest.directives.source('file.sh')
nvtest.directives.link('file.sh')
def test():
    assert os.getenv("BAZ") == "SPAM", os.getenv("BAZ")
if __name__ == "__main__":
    sys.exit(test())
""")
        run = NVTestCommand("run")
        rc = run(".")
        if rc != 0:
            print(open("TestResults/file/nvtest-out.txt").read())
        assert rc == 0


def test_source_rcfile_2(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("file.sh", "w") as fh:
            fh.write("export BAZ=SPAM\n")
        with open("file.pyt", "w") as fh:
            fh.write("""\
import nvtest
import os
import sys
nvtest.directives.link('file.sh')
def test():
    with nvtest.shell.source('file.sh'):
        assert os.getenv("BAZ") == "SPAM", os.getenv("BAZ")
if __name__ == "__main__":
    sys.exit(test())
""")
        run = NVTestCommand("run")
        rc = run(".")
        if rc != 0:
            print(open("TestResults/file/nvtest-out.txt").read())
        assert rc == 0


def test_source(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        path = os.environ["PATH"]
        with open("file", "w") as fh:
            fh.write("export FOO=BAZ\n")
            fh.write("export SPAM=WUBBLE\n")
            fh.write("export PATH=/opt/baz/bin:$PATH\n")
        with shell.source("file"):
            assert os.environ["FOO"] == "BAZ"
            assert os.environ["SPAM"] == "WUBBLE"
            assert os.environ["PATH"] == f"/opt/baz/bin:{path}"
        assert os.environ["PATH"] == path
