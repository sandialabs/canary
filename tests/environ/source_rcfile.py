# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for shell.source() and the source() directive.

Previously test_source_rcfile_1 and test_source_rcfile_2 used
CanaryCommand("run") (subprocess).  They now use Workspace.run() in-process,
which is equivalent and roughly 2× faster.
"""

import os
from pathlib import Path

import canary
from _canary.util import shell
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def run_dir(root: Path) -> None:
    """Collect and run all .pyt files under root; assert returncode 0."""
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        session = workspace.run(specs, only="all")
    assert session.returncode == 0, (
        (root / "TestResults" / "file" / "canary-out.txt").read_text()
        if (root / "TestResults" / "file" / "canary-out.txt").exists()
        else "no output"
    )


def test_source_rcfile_1(tmp_path):
    """source() directive sets env vars inside the test subprocess."""
    root = tmp_path / "rcfile1"
    root.mkdir()

    write(root / "file.sh", "export BAZ=SPAM\n")
    write(
        root / "file.pyt",
        """\
import os
import sys
import canary_pyt
canary_pyt.directives.source('file.sh')
canary_pyt.directives.link('file.sh')
def test():
    assert os.getenv("BAZ") == "SPAM", os.getenv("BAZ")
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    run_dir(root)


def test_source_rcfile_2(tmp_path):
    """canary.shell.source() context manager sets env vars at runtime."""
    root = tmp_path / "rcfile2"
    root.mkdir()

    write(root / "file.sh", "export BAZ=SPAM\n")
    write(
        root / "file.pyt",
        """\
import os
import sys
import canary
import canary_pyt
canary_pyt.directives.link('file.sh')
def test():
    with canary.shell.source('file.sh'):
        assert os.getenv("BAZ") == "SPAM", os.getenv("BAZ")
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    run_dir(root)


def test_source(tmp_path):
    """shell.source() applies env vars to os.environ and cleans up."""
    path = os.environ["PATH"]
    script = tmp_path / "file.sh"
    script.write_text("export FOO=BAZ\nexport SPAM=WUBBLE\nexport PATH=/opt/baz/bin:$PATH\n")
    with shell.source(str(script)):
        assert os.environ["FOO"] == "BAZ"
        assert os.environ["SPAM"] == "WUBBLE"
        assert os.environ["PATH"] == f"/opt/baz/bin:{path}"
    assert os.environ["PATH"] == path
