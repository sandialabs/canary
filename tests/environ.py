import os

from _nvtest.util import shell
from _nvtest.util.filesystem import working_dir


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
